"""Run DocMind with the V2 extractor (page-level routing, structured model).

Everything after extraction is still the V1 pipeline, so differences in the
extraction metrics are caused by the extractor alone.
"""

from __future__ import annotations

import os

os.environ["DOCMIND_EXTRACTOR"] = "v2"

from evaluation.systems import v1 as _v1  # noqa: E402


def run_document(pdf_path, *, embed: bool = True) -> dict:
    out = _v1.run_document(pdf_path, embed=embed)
    if out.get("doc_id"):
        from src.extraction.structured import load_model

        model = load_model(out["doc_id"])
        if model is not None:
            out["ledger"] = model.ledger()
            engines: dict[str, int] = {}
            for p in model.pages:
                engines[p.quality.engine] = engines.get(p.quality.engine, 0) + 1
            out["engine"] = "structured_v2 " + ", ".join(f"{k}:{v}" for k, v in sorted(engines.items()))
            out["pages_needing_review"] = sum(p.quality.needs_review for p in model.pages)
    return out


ask = _v1.ask
