"""
Dual page numbering: physical PDF index vs printed / document page labels.

Physical page (1 = first sheet in the file) stays the source of truth for
bbox resolution, FactTable rows, Chroma metadata, and PDF I/O.

Printed labels come from the PDF ``/PageLabels`` dictionary when present
(e.g. cover ``A``, front matter ``i``/``II``, body ``1``). When labels are
absent, ``printed_page`` stays ``None`` and callers show physical only --
so existing unlabeled corpora keep working unchanged.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger("docmind.provenance")

_ROMAN = re.compile(
    r"^(?=[MDCLXVI])M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PageNumberMap:
    """Cached mapping from 1-indexed physical pages to printed labels."""

    pdf_path: str
    page_count: int
    labels: tuple[str, ...]  # index 0 = physical page 1; may be empty strings
    source: str  # "page_labels" | "identity"

    def printed_label(self, physical_page: int) -> str | None:
        """Return the document/printed label for a physical page, if known."""
        if physical_page < 1 or physical_page > self.page_count:
            return None
        if self.source == "identity":
            return None
        label = self.labels[physical_page - 1].strip()
        return label or None

    def display(self, physical_page: int) -> str:
        """Human-facing page reference (dual when printed differs)."""
        return format_page_reference(
            physical_page, self.printed_label(physical_page)
        )


def format_page_reference(
    physical_page: int,
    printed_page: str | None = None,
) -> str:
    """Format a citation page token.

    Examples:
      - no printed -> ``p.8``
      - printed equals physical arabic -> ``p.8``
      - distinct printed -> ``PDF p.33 (document p.1)``
    """
    phys = int(physical_page)
    printed = (printed_page or "").strip()
    if not printed:
        return f"p.{phys}"
    if printed.isdigit() and int(printed) == phys:
        return f"p.{phys}"
    return f"PDF p.{phys} (document p.{printed})"


def _read_page_labels(pdf_path: Path) -> tuple[str, ...] | None:
    """Return per-page label strings from ``/PageLabels``, or None on failure."""
    try:
        import pypdfium2 as pdfium
    except Exception as exc:  # pragma: no cover
        logger.debug("pypdfium2 unavailable for page labels: %s", exc)
        return None

    try:
        pdf = pdfium.PdfDocument(str(pdf_path))
    except Exception as exc:  # pragma: no cover
        logger.warning("Could not open PDF for page labels %s: %s", pdf_path, exc)
        return None

    try:
        n = len(pdf)
        labels = tuple((pdf.get_page_label(i) or "").strip() for i in range(n))
        return labels
    except Exception as exc:  # pragma: no cover
        logger.warning("Page label read failed for %s: %s", pdf_path, exc)
        return None
    finally:
        try:
            pdf.close()
        except Exception:  # pragma: no cover
            pass


def _labels_are_useful(labels: tuple[str, ...]) -> bool:
    """True when at least one label is non-empty and not a trivial copy of physical."""
    nonempty = [(i + 1, lab) for i, lab in enumerate(labels) if lab]
    if not nonempty:
        return False
    # Useful if any label is non-digit, roman, letter, OR arabic that restarts /
    # differs from the physical index (front-matter + body "1").
    for phys, lab in nonempty:
        if not lab.isdigit():
            return True
        if int(lab) != phys:
            return True
    # All labels are arabic equal to physical -- still "useful" as confirmation,
    # but callers treat printed == physical as a collapsed display. Keep them.
    return True


@lru_cache(maxsize=64)
def _load_page_map_cached(pdf_path: str) -> PageNumberMap:
    path = Path(pdf_path)
    if not path.exists():
        return PageNumberMap(
            pdf_path=pdf_path, page_count=0, labels=(), source="identity"
        )

    labels = _read_page_labels(path)
    if labels is None:
        return PageNumberMap(
            pdf_path=pdf_path, page_count=0, labels=(), source="identity"
        )

    if _labels_are_useful(labels):
        return PageNumberMap(
            pdf_path=pdf_path,
            page_count=len(labels),
            labels=labels,
            source="page_labels",
        )

    return PageNumberMap(
        pdf_path=pdf_path,
        page_count=len(labels),
        labels=labels,
        source="identity",
    )


def load_page_map(pdf_path: str | Path | None) -> PageNumberMap | None:
    """Load (and cache) a PageNumberMap for ``pdf_path``, or None if unavailable."""
    if pdf_path is None:
        return None
    path = Path(pdf_path)
    if not path.exists():
        return None
    return _load_page_map_cached(str(path.resolve()))


def resolve_printed_page(
    pdf_path: str | Path | None,
    physical_page: int,
) -> str | None:
    """Resolve printed/document page label for a physical page, if known."""
    page_map = load_page_map(pdf_path)
    if page_map is None:
        return None
    return page_map.printed_label(int(physical_page))


def clear_page_map_cache() -> None:
    """Test helper: drop cached page maps."""
    _load_page_map_cached.cache_clear()


def looks_like_roman(label: str) -> bool:
    """Whether ``label`` looks like a Roman numeral (front-matter style)."""
    return bool(label and _ROMAN.match(label.strip()))


def enrich_hit_printed_page(
    hit: "EvidenceHit",
    *,
    pdf_path: str | Path | None = None,
) -> "EvidenceHit":
    """Return a copy of ``hit`` with ``printed_page`` filled when resolvable.

    Never mutates the original. No-op when a label is already set or the PDF
    has no ``/PageLabels`` map -- safe for unlabeled corpora.
    """
    from src.query.evidence import EvidenceHit

    if not isinstance(hit, EvidenceHit):
        return hit
    if hit.printed_page is not None:
        return hit

    path = pdf_path
    if path is None and hit.doc_id:
        try:
            from src.pipeline.phase4 import resolve_pdf_path

            path = resolve_pdf_path(hit.doc_id)
        except Exception:  # pragma: no cover
            path = None

    printed = resolve_printed_page(path, hit.page_number)
    if printed is None:
        return hit
    return hit.model_copy(update={"printed_page": printed})
