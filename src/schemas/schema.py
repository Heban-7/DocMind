"""Document schemas: the fixed fields DocMind extracts per document type.

A schema is a YAML file in ``rubric/schemas/`` (see ``invoice.yaml``): its
fields with a type, a description the extractor reads, the words that mark
where each field is printed, and rules checked after extraction. Adding a
document type is adding a file; no code changes.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.config import MODEL_REGISTRY_PATH

SCHEMA_DIR = Path(MODEL_REGISTRY_PATH).parent / "schemas"

FieldType = Literal["text", "date", "code", "money", "number", "list"]
RuleKind = Literal["sum", "sum_of_items", "product_of_item", "not_greater", "date_order", "differ", "ratio_between"]


class ItemField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["text", "number", "money", "date", "code"]
    label: str = ""


class FieldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = ""
    type: FieldType
    label: str = ""
    required: bool = False
    description: str = ""
    find: list[str] = Field(default_factory=list)
    pattern: str | None = Field(default=None, description="a regular expression the stored value must match")
    printed_on: str | None = Field(default=None, description="the page kind (a key of the schema's `pages`) that prints it")
    item: dict[str, ItemField] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _list_needs_items(self) -> "FieldSpec":
        if self.type == "list" and not self.item:
            raise ValueError(f"list field '{self.name}' needs an `item` with its columns")
        return self


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    name: str
    kind: RuleKind
    total: str | None = None
    parts: list[str] = Field(default_factory=list)
    of_list: str | None = Field(default=None, alias="list")  # YAML key `list`
    column: str | None = None
    result: str | None = None
    factors: list[str] = Field(default_factory=list)
    smaller: str | None = None
    larger: str | None = None
    earlier: str | None = None
    later: str | None = None
    tolerance: float = 0.005
    soft: bool = False
    fields_: list[str] = Field(default_factory=list, alias="fields")  # `differ`: these must not be equal
    numerator: str | None = None  # `ratio_between`: numerator / denominator within [min, max]
    denominator: str | None = None
    min: float | None = None
    max: float | None = None

    def fields(self) -> list[str]:
        names = [self.total, self.of_list, self.smaller, self.larger, self.earlier, self.later, self.numerator, self.denominator, *self.parts, *self.fields_]
        return list(dict.fromkeys(n for n in names if n))


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    version: int = 1
    label: str = ""
    description: str = ""
    detect: list[str] = Field(default_factory=list)
    pages: dict[str, list[str]] = Field(default_factory=dict)
    prefer_titles: list[str] = Field(default_factory=list)
    avoid_titles: list[str] = Field(default_factory=list)
    fields: dict[str, FieldSpec]
    rules: list[Rule] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> "Schema":
        for name, spec in self.fields.items():
            spec.name = name
        for name, spec in self.fields.items():
            if spec.printed_on and spec.printed_on not in self.pages:
                raise ValueError(f"field {name!r} is printed on page kind {spec.printed_on!r}, which `pages` does not define")
        for rule in self.rules:
            unknown = [f for f in rule.fields() if f not in self.fields]
            if unknown:
                raise ValueError(f"rule '{rule.name}' names unknown fields: {unknown}")
        return self

    @property
    def id(self) -> str:
        return f"{self.name}@{self.version}"

    def public(self) -> dict:
        """What GET /schemas shows."""
        return {
            "name": self.name,
            "version": self.version,
            "label": self.label,
            "description": self.description,
            "fields": [
                {
                    "name": f.name,
                    "label": f.label or f.name,
                    "type": f.type,
                    "required": f.required,
                    "description": f.description,
                    "columns": {k: v.type for k, v in f.item.items()} if f.type == "list" else None,
                }
                for f in self.fields.values()
            ],
            "rules": [r.name for r in self.rules],
        }


@functools.lru_cache(maxsize=1)
def _load_all() -> dict[str, Schema]:
    out: dict[str, Schema] = {}
    for path in sorted(SCHEMA_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        schema = Schema.model_validate(data)
        out[schema.name] = schema
    return out


def all_schemas() -> dict[str, Schema]:
    return dict(_load_all())


def get_schema(name: str) -> Schema:
    schemas = _load_all()
    if name not in schemas:
        raise KeyError(f"Unknown schema '{name}'. Known: {', '.join(sorted(schemas))}")
    return schemas[name]


def reload() -> None:
    _load_all.cache_clear()
