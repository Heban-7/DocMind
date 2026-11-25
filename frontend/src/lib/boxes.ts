import type { PageBox, PdfBox, ProvenanceCitation } from "./types";

/** A citation box (bottom-left origin) as a box to draw (top-left origin). */
export function fromPdfBox(b: PdfBox, tone: PageBox["tone"] = "primary"): PageBox | null {
  if (!b.page_height || !(b.x1 > b.x0)) return null;
  return { x0: b.x0, x1: b.x1, top: b.page_height - b.y1, bottom: b.page_height - b.y0, tone };
}

function isWholePage(b: PdfBox): boolean {
  return !!b.page_width && !!b.page_height && b.x0 <= 1 && b.y0 <= 1 && b.x1 >= b.page_width - 1 && b.y1 >= b.page_height - 1;
}

/** The boxes a citation marks on its page; empty when only the page is known. */
export function citationBoxes(c: ProvenanceCitation): PageBox[] {
  const list = (c.boxes || []).map((b) => fromPdfBox(b)).filter((b): b is PageBox => !!b);
  if (list.length) return list;
  if (c.bbox && !isWholePage(c.bbox)) {
    const one = fromPdfBox(c.bbox);
    return one ? [one] : [];
  }
  return [];
}

/** What the box on the page shows, in words. */
export function boxNote(kind: string | undefined, n: number): string {
  if (!n) return "This citation points at the whole page.";
  switch (kind) {
    case "fact":
      return "The table cell the figure was read from.";
    case "cell":
      return "The cell that prints the figure, and its row label.";
    case "block":
      return n > 1 ? "The paragraphs the passage came from." : "The paragraph that prints it.";
    default:
      return "The region the citation points at.";
  }
}

/** A field's box ([x0, top, x1, bottom], top-left origin) as a box to draw. */
export function fieldBox(bbox: number[] | null | undefined, label?: string, grounded = true): PageBox[] {
  if (!bbox || bbox.length !== 4) return [];
  const [x0, top, x1, bottom] = bbox;
  // an ungrounded value: the box marks where the model said it read it, not a cell that prints it
  return [{ x0, top, x1, bottom, tone: grounded ? "primary" : "secondary", label }];
}

export function displayFileName(raw?: string): string {
  if (!raw) return "Document.pdf";
  return raw.replace(/^[a-f0-9]{8,32}_/i, "");
}
