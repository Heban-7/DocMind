"""V2 extraction engine: page-level routing into the structured document model.

Saves the full model to ``.refinery/documents/{doc_id}.json`` and the per-page
ledger to ``.refinery/ledger/{doc_id}.jsonl``, and returns Markdown so the
rest of the V1 pipeline (chunker, facts, PageIndex) keeps working until it is
moved onto the model in later milestones.
"""

from __future__ import annotations

import json

from src.config import REFINERY_DIR
from src.document.extract import extract_document
from src.document.model import DocumentModel
from src.document.render import render_markdown
from src.extraction.base import BaseExtractionEngine

DOCUMENTS_DIR = REFINERY_DIR / "documents"
LEDGER_DIR = REFINERY_DIR / "ledger"


class StructuredExtractionEngine(BaseExtractionEngine):
    name = "structured_v2"

    def __init__(self, vision_client=None, allow_vision: bool = True):
        self.vision_client = vision_client
        self.allow_vision = allow_vision
        self.last_model: DocumentModel | None = None

    def extract(self, file_path: str) -> str:
        model = extract_document(file_path, vision_client=self.vision_client, allow_vision=self.allow_vision)
        self.last_model = model
        save_model(model)
        return render_markdown(model)


def save_model(model: DocumentModel) -> None:
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    (DOCUMENTS_DIR / f"{model.doc_id}.json").write_text(model.model_dump_json(), encoding="utf-8")
    (LEDGER_DIR / f"{model.doc_id}.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in model.ledger()), encoding="utf-8"
    )


def load_model(doc_id: str) -> DocumentModel | None:
    path = DOCUMENTS_DIR / f"{doc_id}.json"
    if not path.exists():
        return None
    return DocumentModel.model_validate_json(path.read_text(encoding="utf-8"))
