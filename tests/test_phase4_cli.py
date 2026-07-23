"""Offline tests for Phase 4 indexing glue + query CLI argparse."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.chunking.models import DocumentChunk
from src.pipeline.phase4 import build_query_indexes, resolve_pdf_path
from src.retrieval.vector_store import ChromaLDUStore


class _FakeEmbedder:
    model = "fake"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            base = [0.0] * 8
            for i, ch in enumerate(text.lower()[:64]):
                base[i % 8] += (ord(ch) % 31) / 31.0
            norm = sum(v * v for v in base) ** 0.5 or 1.0
            out.append([v / norm for v in base])
        return out


def _write_chunks(tmp_path: Path, doc_id: str) -> Path:
    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    chunks = [
        DocumentChunk.create(
            "Import tax expenditures were ETB 120.7 billion in FY 2020/21.",
            parent_hierarchy=["Executive summary"],
            page_numbers=[4],
            chunk_type="prose",
        ),
        DocumentChunk.create(
            "Governance notes.",
            parent_hierarchy=["Governance"],
            page_numbers=[10],
            chunk_type="prose",
        ),
    ]
    path = chunks_dir / f"{doc_id}.jsonl"
    path.write_text(
        "\n".join(c.model_dump_json() for c in chunks) + "\n",
        encoding="utf-8",
    )
    return chunks_dir


def test_build_query_indexes_without_embed(tmp_path: Path):
    chunks_dir = _write_chunks(tmp_path, "p4doc")
    result = build_query_indexes(
        "p4doc",
        document_name="sample.pdf",
        chunks_dir=chunks_dir,
        embed=False,
        pageindex_llm_client=None,
        fact_store=__import__("src.facts.store", fromlist=["FactStore"]).FactStore(
            tmp_path / "facts.db"
        ),
    )
    assert result.pageindex_path is not None
    assert result.pageindex_path.exists()
    assert result.pageindex_sections >= 1
    assert result.facts_written >= 1
    assert result.embedded is False
    assert result.chunks_embedded == 0


def test_build_query_indexes_with_fake_embed(tmp_path: Path):
    from src.facts.store import FactStore

    chunks_dir = _write_chunks(tmp_path, "p4emb")
    chroma = ChromaLDUStore(persist_dir=tmp_path / "chroma", collection_name="p4emb")
    result = build_query_indexes(
        "p4emb",
        document_name="sample.pdf",
        chunks_dir=chunks_dir,
        embed=True,
        pageindex_llm_client=None,
        chroma_store=chroma,
        fact_store=FactStore(tmp_path / "facts.db"),
        embedder=_FakeEmbedder(),
    )
    assert result.embedded is True
    assert result.chunks_embedded == 2
    assert result.chroma_total == 2


def test_build_query_indexes_missing_chunks(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        build_query_indexes("nope", chunks_dir=tmp_path, embed=False)


def test_resolve_pdf_path_explicit(tmp_path: Path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF")
    assert resolve_pdf_path("any", pdf) == pdf
    assert resolve_pdf_path("any", tmp_path / "missing.pdf") is None


def test_run_query_cli_help():
    from run_query import main

    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_run_query_cli_requires_text_or_index():
    from run_query import main

    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2
