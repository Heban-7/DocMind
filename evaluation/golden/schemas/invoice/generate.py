"""Generate the invoice test set: 20 invoice PDFs with exact answers.

No public invoice set had both the PDFs and a clear licence (MIDD, CC BY 4.0,
ships token annotations only; others are non-commercial or behind a login),
so the set is generated, reproducibly (fixed seed):

- fictional Ethiopian sellers and buyers, 10-digit TINs, 15% VAT (some 0%),
  ETB and a few USD invoices;
- five layouts: classic, banded, compact, bilingual Amharic/English, and one
  full of look-alike numbers (order number, delivery note, previous balance,
  amount in words);
- two invoices run over two pages;
- six are "scanned": rasterised at 150 dpi, slightly rotated, blurred,
  noised and saved as image-only PDFs, so they go through OCR.

    python -m evaluation.golden.schemas.invoice.generate [--out data/synthetic/invoices]

Writes the PDFs to --out (not committed: they are rebuilt from this script)
and labels.jsonl + documents.json next to this file (committed).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SEED = 20261125

SELLERS = [
    ("Abay Office Supplies PLC", "Bole Sub-city, Woreda 03, H.No 1120, Addis Ababa"),
    ("Entoto Logistics S.C.", "Kirkos Sub-city, Woreda 08, Africa Avenue, Addis Ababa"),
    ("Lalibela Printing Enterprise", "Arada Sub-city, Woreda 01, Churchill Road, Addis Ababa"),
    ("Sheger Agro Industries PLC", "Akaki Kality Sub-city, Woreda 05, Addis Ababa"),
    ("Awash Tech Solutions PLC", "Yeka Sub-city, Woreda 11, CMC Road, Addis Ababa"),
    ("Tana Furniture Manufacturing PLC", "Bahir Dar, Kebele 14, Bahir Dar"),
    ("Gondar Medical Supplies S.C.", "Lideta Sub-city, Woreda 07, Addis Ababa"),
    ("Simien Construction Materials PLC", "Nifas Silk-Lafto Sub-city, Woreda 02, Addis Ababa"),
]
BUYERS = [
    ("Blue Nile Hotel and Resort S.C.", "Bahir Dar, Kebele 03"),
    ("Rift Valley Microfinance S.C.", "Hawassa, Tabor Sub-city"),
    ("Harar Brewery Distributors PLC", "Dire Dawa, Kezira"),
    ("Addis Ababa Science Academy", "Gulele Sub-city, Woreda 09, Addis Ababa"),
    ("Mekelle Cement Traders PLC", "Mekelle, Hadnet Sub-city"),
    ("Omo Valley Coffee Exporters PLC", "Jimma, Ginjo Kebele"),
    ("Danakil Mining Services S.C.", "Semera, Kebele 01"),
    ("Wolaita Sodo General Hospital", "Wolaita Sodo, Kebele 02"),
]
PRODUCTS = [
    ("A4 copy paper, 80 gsm (ream)", 380.0, 1),
    ("Toner cartridge, HP 26A", 6200.0, 1),
    ("Office chair, ergonomic", 8750.0, 1),
    ("Steel filing cabinet, 4 drawers", 14200.0, 1),
    ("Delivery and handling", 1500.0, 0),
    ("Laptop, 14 inch, 16 GB RAM", 68500.0, 1),
    ("Network switch, 24 port", 23900.0, 1),
    ("Cement, OPC 50 kg (bag)", 1180.0, 1),
    ("Reinforcement bar, 12 mm (piece)", 865.5, 1),
    ("Surgical gloves (box of 100)", 640.0, 1),
    ("Printing, annual report (copy)", 412.75, 1),
    ("Installation service (hour)", 950.0, 0),
    ("Coffee, washed Yirgacheffe (kg)", 1325.0, 1),
    ("Diesel transport, Addis to Adama (trip)", 18400.0, 0),
    ("Maintenance contract, quarterly", 27500.0, 0),
    ("Whiteboard marker (box of 12)", 315.0, 1),
    ("LED floodlight, 100 W", 3480.0, 1),
    ("Training workshop (participant)", 2250.0, 0),
]
DATE_FORMATS = {
    "classic": lambda d: d.strftime("%d/%m/%Y"),
    "banded": lambda d: d.strftime("%B %d, %Y").replace(" 0", " "),
    "compact": lambda d: d.isoformat(),
    "bilingual": lambda d: d.strftime("%d %b %Y"),
    "distractors": lambda d: d.strftime("%d-%m-%Y"),
}


@dataclass
class Line:
    description: str
    quantity: float
    unit_price: float

    @property
    def amount(self) -> float:
        return round(self.quantity * self.unit_price, 2)


@dataclass
class Invoice:
    key: str
    layout: str
    number: str
    issued: date
    due: date | None
    seller: tuple[str, str]
    seller_tin: str
    buyer: tuple[str, str]
    buyer_tin: str | None
    currency: str
    vat_rate: float
    lines: list[Line] = field(default_factory=list)
    scanned: bool = False

    @property
    def subtotal(self) -> float:
        return round(sum(line.amount for line in self.lines), 2)

    @property
    def vat(self) -> float:
        return round(self.subtotal * self.vat_rate, 2)

    @property
    def total(self) -> float:
        return round(self.subtotal + self.vat, 2)

    def labels(self) -> dict:
        return {
            "invoice_number": self.number,
            "invoice_date": self.issued.isoformat(),
            "due_date": self.due.isoformat() if self.due else None,
            "seller_name": self.seller[0],
            "seller_tin": self.seller_tin,
            "buyer_name": self.buyer[0],
            "buyer_tin": self.buyer_tin,
            "currency": self.currency,
            "subtotal": self.subtotal,
            "vat_amount": self.vat,
            "total_amount": self.total,
            "line_items": [
                {"description": ln.description, "quantity": ln.quantity, "unit_price": ln.unit_price, "amount": ln.amount}
                for ln in self.lines
            ],
        }


def money(v: float, currency: str = "") -> str:
    s = f"{v:,.2f}"
    return f"{currency} {s}".strip()


def qty(v: float) -> str:
    return f"{v:g}"


def _tin(rng: random.Random) -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(10))


def make_invoices() -> list[Invoice]:
    rng = random.Random(SEED)
    layouts = ["classic", "banded", "compact", "bilingual", "distractors"] * 4
    scanned = {2, 5, 9, 12, 16, 19}  # six of twenty
    long_ones = {7, 14}  # two run over two pages
    out = []
    for i, layout in enumerate(layouts):
        issued = date(2025, 7, 8) + timedelta(days=rng.randint(0, 330))
        due = issued + timedelta(days=rng.choice([15, 30, 30, 45, 60])) if rng.random() < 0.75 else None
        currency = "USD" if i in (6, 13) else "ETB"
        n_lines = rng.randint(42, 48) if i in long_ones else rng.randint(1, 8)
        lines = []
        for _ in range(n_lines):
            desc, price, _vatable = rng.choice(PRODUCTS)
            if currency == "USD":
                price = round(price / 140.0, 2)
            q = rng.choice([1, 1, 2, 3, 4, 5, 6, 10, 12, 20, 25, 2.5, 0.5])
            lines.append(Line(desc, float(q), float(price)))
        number = {
            "classic": f"INV-{issued.year}-{rng.randint(100, 9999):04d}",
            "banded": f"{rng.randint(10000, 99999)}",
            "compact": f"AT/{issued.year % 100:02d}/{rng.randint(1, 999):03d}",
            "bilingual": f"FS {rng.randint(1000, 99999)}",
            "distractors": f"SI-{rng.randint(100000, 999999)}",
        }[layout]
        out.append(
            Invoice(
                key=f"inv_{i + 1:02d}",
                layout=layout,
                number=number,
                issued=issued,
                due=due,
                seller=SELLERS[i % len(SELLERS)],
                seller_tin=_tin(rng),
                buyer=BUYERS[(i * 3 + 1) % len(BUYERS)],
                buyer_tin=_tin(rng) if rng.random() < 0.8 else None,
                currency=currency,
                vat_rate=0.0 if i in (4, 11) else 0.15,
                lines=lines,
                scanned=i in scanned,
            )
        )
    return out


# --- drawing --------------------------------------------------------------------------


def _fonts() -> tuple[str, str, str | None]:
    """Regular, bold, and an Ethiopic font when this machine has one (else None)."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    ethiopic = None
    for path in (
        "C:/Windows/Fonts/nyala.ttf",
        "/usr/share/fonts/truetype/abyssinica/AbyssinicaSIL-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansEthiopic-Regular.ttf",
    ):
        if Path(path).exists():
            pdfmetrics.registerFont(TTFont("Ethiopic", path))
            ethiopic = "Ethiopic"
            break
    return "Helvetica", "Helvetica-Bold", ethiopic


class Pager:
    """A canvas that starts a new page when the table runs out of room."""

    def __init__(self, c, height: float, top_margin: float = 60):
        self.c, self.height, self.top = c, height, top_margin
        self.page = 1

    def need(self, y: float, room: float, redraw) -> float:
        if y - room > 70:
            return y
        self.c.showPage()
        self.page += 1
        redraw(self.page)
        return self.height - self.top - 40


def draw_invoice(inv: Invoice, path: Path) -> dict:
    """Draw ``inv`` to ``path``; returns the page each field is printed on."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    regular, bold, ethiopic = _fonts()
    w, h = A4
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle(f"Invoice {inv.number}")
    fmt = DATE_FORMATS[inv.layout]
    cur = inv.currency
    pages = {}

    def text(x, y, s, size=10, font=regular, color=colors.black, right=False):
        if ethiopic and any("ሀ" <= ch <= "፿" for ch in s):
            font = ethiopic  # Nyala / Abyssinica carry Latin glyphs too
        c.setFont(font, size)
        c.setFillColor(color)
        (c.drawRightString if right else c.drawString)(x, y, s)

    def label(en: str, am: str | None = None) -> str:
        return f"{am} / {en}" if (am and inv.layout == "bilingual" and ethiopic) else en

    def am_text(x, y, s, size=10):
        if ethiopic:
            text(x, y, s, size, ethiopic)

    # header -------------------------------------------------------------------------
    if inv.layout == "banded":
        c.setFillColor(colors.HexColor("#1f4e79"))
        c.rect(0, h - 95, w, 95, stroke=0, fill=1)
        text(40, h - 50, inv.seller[0], 18, bold, colors.white)
        text(40, h - 70, inv.seller[1], 9, regular, colors.white)
        text(w - 40, h - 50, "INVOICE", 22, bold, colors.white, right=True)
        y = h - 130
    else:
        text(40, h - 60, inv.seller[0], 15, bold)
        text(40, h - 76, inv.seller[1], 9)
        title = {"classic": "TAX INVOICE", "compact": "Invoice", "bilingual": "INVOICE", "distractors": "SALES INVOICE"}[inv.layout]
        text(w - 40, h - 60, title, 18, bold, right=True)
        if inv.layout == "bilingual":
            am_text(w - 150, h - 80, "የሽያጭ ደረሰኝ", 12)
        y = h - 110
    text(40, y, f"{label('TIN', 'ግብር ከፋይ መለያ ቁጥር')}: {inv.seller_tin}", 9)
    if inv.layout == "distractors":
        text(40, y - 14, "VAT Reg. No: " + inv.seller_tin[:7], 9)
        text(40, y - 28, "Tel: +251 11 " + inv.seller_tin[3:6] + " " + inv.seller_tin[6:10], 9)

    # invoice block ----------------------------------------------------------------------
    rows = [(label("Invoice No", "ደረሰኝ ቁጥር"), inv.number), (label("Date", "ቀን"), fmt(inv.issued))]
    if inv.due:
        rows.append((label("Due Date", "የክፍያ ቀን"), fmt(inv.due)))
    if inv.layout == "distractors":
        rows = [("P.O. Number", f"PO-{int(inv.seller_tin[:5]) % 90000 + 10000}"),
                ("Delivery Note", f"DN {int(inv.seller_tin[2:6]) + 1000}")] + rows
    if inv.layout == "compact":
        rows = [("Invoice #", inv.number), ("Issued", fmt(inv.issued))] + ([("Payment due", fmt(inv.due))] if inv.due else [])
    by = y
    for k, v in rows:
        text(w - 200, by, f"{k}:", 9, bold)
        text(w - 40, by, v, 9, right=True)
        by -= 14
    pages.update(invoice_number=1, invoice_date=1, due_date=1, seller_name=1, seller_tin=1)

    # parties ------------------------------------------------------------------------------
    y = min(by, y - 40) - 25
    head = {"classic": "Bill To", "banded": "Billed To", "compact": "Customer", "bilingual": "Bill To", "distractors": "Sold To"}[inv.layout]
    text(40, y, label(head, "ገዢ"), 10, bold)
    text(40, y - 14, inv.buyer[0], 10)
    text(40, y - 27, inv.buyer[1], 9)
    if inv.buyer_tin:
        text(40, y - 40, f"{label('Customer TIN', 'የገዢ መለያ ቁጥር')}: {inv.buyer_tin}", 9)
    pages.update(buyer_name=1, buyer_tin=1)
    if inv.layout == "distractors":
        text(w - 220, y, "Previous balance:", 9, bold)
        text(w - 40, y, money(round(inv.total * 0.37, 2), cur), 9, right=True)
        text(w - 220, y - 14, "Credit limit:", 9, bold)
        text(w - 40, y - 14, money(500000.0, cur), 9, right=True)

    # line items -----------------------------------------------------------------------------
    y -= 70
    cols = [40, 300, 360, 460, w - 40]  # description | qty | unit price | amount (right edges after the first)

    def table_head(yy):
        if inv.layout != "compact":
            c.setFillColor(colors.HexColor("#d9e2f3" if inv.layout == "banded" else "#eeeeee"))
            c.rect(36, yy - 4, w - 72, 16, stroke=0, fill=1)
        heads = ["Description", "Qty", f"Unit Price ({cur})", f"Amount ({cur})"]
        if inv.layout == "bilingual" and ethiopic:
            heads = ["ዝርዝር / Description", "ብዛት / Qty", f"ያንዱ ዋጋ / Unit ({cur})", f"ጠቅላላ / Amount ({cur})"]
        f = ethiopic if (inv.layout == "bilingual" and ethiopic) else bold
        text(cols[0] + 4, yy, heads[0], 9, f)
        for i, hd in enumerate(heads[1:], start=1):
            text(cols[i + 1] - 4 if i < 3 else cols[4] - 4, yy, hd, 9, f, right=True)
        return yy - 18

    def redraw(page_no):
        text(40, h - 50, f"{inv.seller[0]}  ·  Invoice {inv.number}  ·  page {page_no}", 9, bold)

    pager = Pager(c, h)
    y = table_head(y)
    for i, ln in enumerate(inv.lines, start=1):
        new_y = pager.need(y, 16, redraw)
        if new_y != y:
            y = table_head(new_y)
        text(cols[0] + 4, y, f"{i}. {ln.description}" if inv.layout == "compact" else ln.description, 9)
        text(cols[2] - 4, y, qty(ln.quantity), 9, right=True)
        text(cols[3] - 4, y, money(ln.unit_price), 9, right=True)
        text(cols[4] - 4, y, money(ln.amount), 9, right=True)
        if inv.layout in ("classic", "bilingual"):
            c.setStrokeColor(colors.HexColor("#cccccc"))
            c.line(36, y - 4, w - 36, y - 4)
        y -= 16
    pages["line_items"] = 1 if pager.page == 1 else [1, pager.page]

    # totals ---------------------------------------------------------------------------------
    y = pager.need(y, 90, redraw) - 10
    totals = [
        (label("Subtotal", "ድምር"), money(inv.subtotal, cur)),
        (label(f"VAT {inv.vat_rate * 100:g}%", "ተ.እ.ታ"), money(inv.vat, cur)),
        (label("Total", "ጠቅላላ ድምር"), money(inv.total, cur)),
    ]
    if inv.layout == "banded":
        totals[-1] = ("Amount Due", money(inv.total, cur))
    if inv.layout == "compact":
        totals = [("Sub-total", money(inv.subtotal, cur)), ("Tax", money(inv.vat, cur)), ("Total payable", money(inv.total, cur))]
    for k, v in totals:
        text(w - 230, y, k, 10, bold)
        text(w - 44, y, v, 10, bold if k in ("Total", "Amount Due", "Total payable") or "ጠቅላላ" in k else regular, right=True)
        y -= 16
    page_of_totals = pager.page
    pages.update(subtotal=page_of_totals, vat_amount=page_of_totals, total_amount=page_of_totals, currency=1)
    if inv.layout == "distractors":
        text(40, y - 6, f"Amount in words: {_words(inv.total)} {'Birr' if cur == 'ETB' else 'US Dollars'} only", 9)
        text(40, y - 22, f"Balance after this invoice: {money(round(inv.total * 1.37, 2), cur)}", 9)
    text(40, 60, "Thank you for your business. Payment by bank transfer to the account on file.", 8, regular, colors.grey)
    c.showPage()
    c.save()
    return pages


_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def _words(v: float) -> str:
    n = int(v)

    def under_1000(x: int) -> str:
        parts = []
        if x >= 100:
            parts.append(f"{_ONES[x // 100]} hundred")
            x %= 100
        if x >= 20:
            parts.append(_TENS[x // 10] + (f"-{_ONES[x % 10]}" if x % 10 else ""))
        elif x:
            parts.append(_ONES[x])
        return " ".join(parts)

    out = []
    for size, name in ((10**6, "million"), (10**3, "thousand")):
        if n >= size:
            out.append(f"{under_1000(n // size)} {name}")
            n %= size
    if n or not out:
        out.append(under_1000(n) or "zero")
    return " ".join(out).capitalize()


def scan(pdf_path: Path, rng: random.Random) -> None:
    """Turn a digital PDF into what a scanner gives: page images, a little crooked and noisy."""
    import pypdfium2 as pdfium
    from PIL import Image, ImageFilter

    pdf = pdfium.PdfDocument(str(pdf_path))
    images = []
    for page in pdf:
        img = page.render(scale=150 / 72).to_pil().convert("L")
        img = img.rotate(rng.uniform(-1.2, 1.2), resample=Image.BICUBIC, expand=False, fillcolor=255)
        img = img.filter(ImageFilter.GaussianBlur(0.6))
        noise = Image.effect_noise(img.size, 18).convert("L")
        img = Image.blend(img, noise, 0.08)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=70)
        images.append(Image.open(io.BytesIO(buf.getvalue())).convert("L"))
    pdf.close()
    images[0].save(pdf_path, "PDF", resolution=150.0, save_all=True, append_images=images[1:])


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data" / "synthetic" / "invoices"))
    args = ap.parse_args(argv)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED + 1)
    labels, docs = [], []
    for inv in make_invoices():
        path = out_dir / f"{inv.key}.pdf"
        pages = draw_invoice(inv, path)
        if inv.scanned:
            scan(path, rng)
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        labels.append({"doc_key": inv.key, "schema": "invoice", "fields": inv.labels(), "pages": pages, "status": "exact"})
        docs.append({"doc_key": inv.key, "file_name": path.name, "layout": inv.layout, "scanned": inv.scanned, "sha256": sha})
        print(f"{inv.key}: {inv.layout:11s} {'scanned' if inv.scanned else 'digital'} {len(inv.lines):2d} lines  total {money(inv.total, inv.currency)}")
    (HERE / "labels.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in labels), encoding="utf-8")
    (HERE / "documents.json").write_text(
        json.dumps({"schema": "invoice", "generator": "evaluation/golden/schemas/invoice/generate.py", "seed": SEED, "corpus_dir": "data/synthetic/invoices", "documents": docs}, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
