"""
DocMind | Ingest one PDF from the command line.

    PDF --> V2 extraction (per page) --> chunks --> PageIndex + FactTable
        --> pgvector, all in Postgres under the local CLI account

Usage:
    uv run python run_pipeline.py                      # sample.pdf
    uv run python run_pipeline.py path/to/other.pdf
    uv run python run_pipeline.py --skip-embed         # no embedding API cost

Needs the dev database (docker compose -f docker-compose.dev.yml up -d db).
"""

from __future__ import annotations

import argparse

from src.config import DEFAULT_SAMPLE_PDF


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest one PDF into DocMind (local CLI account).")
    parser.add_argument("pdf", nargs="?", default=str(DEFAULT_SAMPLE_PDF), help="Path to a PDF.")
    parser.add_argument("--skip-embed", action="store_true", help="Index without embeddings (no API cost).")
    args = parser.parse_args()

    from src.db.local import local_principal
    from src.db.migrate import migrate
    from src.pipeline.ingest import ingest_document

    migrate()
    result = ingest_document(args.pdf, principal=local_principal(), embed=not args.skip_embed)

    print("=" * 72)
    print("DocMind | Ingest")
    print("=" * 72)
    print(f"File            : {result.file_name}")
    print(f"Document ID     : {result.document_id}")
    print(f"Status          : {result.status}" + (" (already ingested)" if result.deduplicated else ""))
    print(f"Pages           : {result.page_count}")
    if not result.deduplicated:
        print(f"Engines         : {', '.join(f'{k}:{v}' for k, v in result.engines.items())}")
        print(f"Chunks / facts  : {result.chunk_count} / {result.facts_written}")
        print(f"Seconds         : {result.stats.get('seconds')}")
    print(f"Pages to review : {result.pages_needing_review}")
    print("=" * 72)
    print(f'Ask: uv run python run_query.py "your question" --doc {result.document_id}')


if __name__ == "__main__":
    main()
