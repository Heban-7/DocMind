"""Schema fields: extract, read, review, export (M8).

    GET    /schemas                                  the document types and their fields
    POST   /documents/{id}/fields   {"schema": ...}  queue an extraction (202)
    GET    /documents/{id}/fields?schema=...         the latest extraction, with page and box per field
    PATCH  /documents/{id}/fields/{field}            a person confirms, corrects or rejects a field
    GET    /review                                   every field waiting for a person
    GET    /exports/{schema}.csv | .xlsx             one row per document (?document_id=... to choose)
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from src.api.dependencies import get_principal
from src.db.repos import AccessDeniedError, Principal
from src.llm.errors import SpendingCapError
from src.schemas import service
from src.schemas.schema import get_schema

logger = logging.getLogger("docmind.api")

fields_router = APIRouter(tags=["fields"])


class ExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_name: str = Field(alias="schema", min_length=1, max_length=80)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["confirm", "correct", "reject"]
    value: Any = None
    schema_name: str | None = Field(default=None, alias="schema", max_length=80)


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc).strip("'") or "Not found.")


@fields_router.get("/schemas")
def schemas(principal: Principal = Depends(get_principal)) -> dict:  # noqa: ARG001 - signed-in users only
    return {"schemas": service.schemas_public()}


@fields_router.post("/documents/{doc_id}/fields", status_code=status.HTTP_202_ACCEPTED)
def extract(doc_id: str, payload: ExtractRequest, principal: Principal = Depends(get_principal)) -> dict:
    try:
        return service.request_extraction(principal, doc_id, payload.schema_name)
    except AccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.") from exc
    except KeyError as exc:
        raise _not_found(exc) from exc
    except SpendingCapError as exc:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@fields_router.get("/documents/{doc_id}/fields")
def fields(doc_id: str, schema: str | None = Query(default=None, max_length=80), principal: Principal = Depends(get_principal)) -> dict:
    try:
        return service.latest_extraction(principal, doc_id, schema)
    except AccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.") from exc
    except KeyError as exc:
        raise _not_found(exc) from exc


@fields_router.patch("/documents/{doc_id}/fields/{field}")
def review(doc_id: str, field: str, payload: ReviewRequest, principal: Principal = Depends(get_principal)) -> dict:
    try:
        return service.review_field(principal, doc_id, field, action=payload.action, value=payload.value, schema_name=payload.schema_name)
    except AccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.") from exc
    except KeyError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@fields_router.get("/review")
def review_queue(limit: int = Query(default=100, ge=1, le=500), principal: Principal = Depends(get_principal)) -> dict:
    return {"fields": service.review_queue(principal, limit=limit)}


@fields_router.get("/exports/{schema}.{fmt}")
def export(
    schema: str,
    fmt: Literal["csv", "xlsx"],
    document_id: list[str] | None = Query(default=None),
    principal: Principal = Depends(get_principal),
) -> Response:
    try:
        spec = get_schema(schema)
        columns, rows, items = service.export_table(principal, schema, document_id)
    except AccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.") from exc
    except KeyError as exc:
        raise _not_found(exc) from exc
    name = f"docmind-{schema}"
    if fmt == "csv":
        return Response(
            service.to_csv(columns, rows), media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{name}.csv"'},
        )
    return Response(
        service.to_xlsx(spec, columns, rows, items),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'},
    )
