# build_bible.py
# MarketOS — "The Complete Build Bible" PDF renderer.
#
# Content lives in bible_content_a/b/c.py as a flat list of (kind, payload)
# blocks. This file owns nothing but layout: styles, the block dispatcher,
# the running header/footer canvas, and the table-of-contents page.
#
#   python build_bible.py            -> MARKETOS_BUILD_BIBLE.pdf
#   python build_bible.py out.pdf    -> out.pdf
#
# Block kinds (see bible_content_*.py):
#   ("part",  (number, title, standfirst))    full-bleed part divider
#   ("h2",    "2.3 Title")                    section heading
#   ("h3",    "SUBHEADING")                   small caps sub-heading
#   ("p",     "text")                         body paragraph (reportlab inline tags ok)
#   ("bul",   ["item", ...])                  bullet list
#   ("num",   ["item", ...])                  numbered list
#   ("code",  "monospace block")              fixed-width block, no wrapping
#   ("box",   (title, body))                  accent callout
#   ("warn",  (title, body))                  red "honest negative" callout
#   ("table", (col_widths, [[cells], ...]))   first row is the header
#   ("alts",  [[option, gain, cost, verdict], ...])
#                                             alternatives table, fixed header
#   ("rule",  None)                           thin horizontal rule
#   ("pb",    None)                           page break

import sys
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as _canvas
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether, ListFlowable, ListItem, HRFlowable, Preformatted,
    NextPageTemplate,
)

# ── palette ───────────────────────────────────────────────────────
INK      = colors.HexColor("#0B1220")   # near-black body text
SLATE    = colors.HexColor("#334155")   # secondary text
MUTED    = colors.HexColor("#64748B")   # captions, footers
ACCENT   = colors.HexColor("#0E7490")   # teal — headings, rules
ACCENT_L = colors.HexColor("#ECFEFF")   # teal wash — callout background
ACCENT_B = colors.HexColor("#A5F3FC")   # teal border
DANGER   = colors.HexColor("#B91C1C")   # red — honest negatives
DANGER_L = colors.HexColor("#FEF2F2")
DANGER_B = colors.HexColor("#FECACA")
CODE_BG  = colors.HexColor("#F1F5F9")
CODE_BR  = colors.HexColor("#CBD5E1")
LINE     = colors.HexColor("#E2E8F0")
COVER_BG = colors.HexColor("#071019")

PAGE_W, PAGE_H = A4
MARGIN_L = 20 * mm
MARGIN_R = 18 * mm
MARGIN_T = 20 * mm
MARGIN_B = 20 * mm
BODY_W   = PAGE_W - MARGIN_L - MARGIN_R

DOC_TITLE = "MarketOS — The Complete Build Bible"

# ── styles ────────────────────────────────────────────────────────
S = {}
S["body"] = ParagraphStyle(
    "body", fontName="Helvetica", fontSize=9.1, leading=13.4,
    textColor=INK, alignment=TA_JUSTIFY, spaceAfter=6,
)
S["part_no"] = ParagraphStyle(
    "part_no", fontName="Helvetica-Bold", fontSize=10, leading=13,
    textColor=ACCENT, spaceAfter=4, alignment=TA_CENTER,
)
S["part_title"] = ParagraphStyle(
    "part_title", fontName="Helvetica-Bold", fontSize=25, leading=30,
    textColor=INK, spaceAfter=8, alignment=TA_CENTER,
)
S["part_stand"] = ParagraphStyle(
    "part_stand", fontName="Helvetica-Oblique", fontSize=10, leading=15,
    textColor=SLATE, alignment=TA_CENTER, spaceAfter=4,
)
S["h2"] = ParagraphStyle(
    "h2", fontName="Helvetica-Bold", fontSize=13.5, leading=17,
    textColor=ACCENT, spaceBefore=13, spaceAfter=5,
)
S["h3"] = ParagraphStyle(
    "h3", fontName="Helvetica-Bold", fontSize=8.4, leading=11.5,
    textColor=SLATE, spaceBefore=8, spaceAfter=3,
)
S["bullet"] = ParagraphStyle(
    "bullet", parent=S["body"], spaceAfter=2.5, alignment=TA_JUSTIFY,
)
S["code"] = ParagraphStyle(
    "code", fontName="Courier", fontSize=7.3, leading=9.6, textColor=INK,
)
S["box_t"] = ParagraphStyle(
    "box_t", fontName="Helvetica-Bold", fontSize=7.8, leading=10.5,
    textColor=ACCENT, spaceAfter=3,
)
S["box_b"] = ParagraphStyle(
    "box_b", fontName="Helvetica", fontSize=8.7, leading=12.6, textColor=INK,
    alignment=TA_JUSTIFY,
)
S["warn_t"] = ParagraphStyle(
    "warn_t", parent=S["box_t"], textColor=DANGER,
)
S["th"] = ParagraphStyle(
    "th", fontName="Helvetica-Bold", fontSize=7.7, leading=10,
    textColor=colors.white,
)
S["td"] = ParagraphStyle(
    "td", fontName="Helvetica", fontSize=7.7, leading=10.2, textColor=INK,
)
S["toc_h"] = ParagraphStyle(
    "toc_h", fontName="Helvetica-Bold", fontSize=9, leading=11.6,
    textColor=ACCENT, spaceBefore=6, spaceAfter=1.5,
)
S["toc_i"] = ParagraphStyle(
    "toc_i", fontName="Helvetica", fontSize=7.9, leading=10.3, textColor=SLATE,
)


# ── page furniture ────────────────────────────────────────────────
class BibleCanvas(_canvas.Canvas):
    """Two-pass canvas so the footer can print 'Page n / total'."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._pages = []

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for state in self._pages:
            self.__dict__.update(state)
            if self._pageNumber > 1:
                self._furniture(total)
            super().showPage()
        super().save()

    def _furniture(self, total):
        self.saveState()
        self.setFont("Helvetica", 6.8)
        self.setFillColor(MUTED)
        self.drawString(MARGIN_L, PAGE_H - MARGIN_T + 7 * mm, DOC_TITLE.upper())
        self.setStrokeColor(LINE)
        self.setLineWidth(0.5)
        self.line(MARGIN_L, PAGE_H - MARGIN_T + 5.5 * mm,
                  PAGE_W - MARGIN_R, PAGE_H - MARGIN_T + 5.5 * mm)
        self.line(MARGIN_L, MARGIN_B - 5 * mm, PAGE_W - MARGIN_R, MARGIN_B - 5 * mm)
        self.setFont("Helvetica", 6.8)
        self.drawString(MARGIN_L, MARGIN_B - 9 * mm,
                        "Private engineering reference — not investment advice")
        self.drawRightString(PAGE_W - MARGIN_R, MARGIN_B - 9 * mm,
                             f"Page {self._pageNumber} / {total}")
        self.restoreState()


def draw_cover(canv, doc):
    canv.saveState()
    canv.setFillColor(COVER_BG)
    canv.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    canv.setFillColor(ACCENT)
    canv.rect(0, PAGE_H - 12 * mm, PAGE_W, 12 * mm, fill=1, stroke=0)
    canv.setFillColor(colors.HexColor("#7DD3FC"))
    canv.rect(0, PAGE_H - 13.6 * mm, PAGE_W, 1.6 * mm, fill=1, stroke=0)

    canv.setFillColor(colors.HexColor("#67E8F9"))
    canv.setFont("Helvetica-Bold", 9)
    canv.drawCentredString(PAGE_W / 2, PAGE_H - 62 * mm,
                           "A   C O M P L E T E ,   F R O M - Z E R O   E N G I N E E R I N G   G U I D E")

    canv.setFillColor(colors.white)
    canv.setFont("Helvetica-Bold", 46)
    canv.drawCentredString(PAGE_W / 2, PAGE_H - 88 * mm, "MarketOS")
    canv.setFont("Helvetica", 17)
    canv.setFillColor(colors.HexColor("#CBD5E1"))
    canv.drawCentredString(PAGE_W / 2, PAGE_H - 101 * mm, "The Complete Build Bible")

    canv.setStrokeColor(colors.HexColor("#155E75"))
    canv.setLineWidth(0.8)
    canv.line(45 * mm, PAGE_H - 110 * mm, PAGE_W - 45 * mm, PAGE_H - 110 * mm)

    canv.setFont("Helvetica", 9.6)
    canv.setFillColor(colors.HexColor("#94A3B8"))
    for i, line in enumerate([
        "Start knowing nothing. Finish able to build — and defend — a measured,",
        "production-shaped quantitative research system for Indian equities.",
        "Every concept defined, every design decision justified, every alternative",
        "named, with worked examples for all the maths.",
    ]):
        canv.drawCentredString(PAGE_W / 2, PAGE_H - (121 + i * 5.6) * mm, line)

    canv.setFont("Helvetica", 8.4)
    canv.setFillColor(colors.HexColor("#67E8F9"))
    canv.drawCentredString(
        PAGE_W / 2, PAGE_H - 156 * mm,
        "Sector-relative alpha over 130 NSE listings · macro regime · ML forecasts · "
        "Markowitz MVO · walk-forward proof")
    canv.setFillColor(colors.HexColor("#64748B"))
    canv.setFont("Helvetica", 8)
    canv.drawCentredString(
        PAGE_W / 2, PAGE_H - 163 * mm,
        "Reference stack: Python 3.10+ · SQLAlchemy/PostgreSQL · scikit-learn/XGBoost/LightGBM · SciPy "
        "SLSQP · Flask · yfinance · Groq LLM · zero paid data feeds · deployed and automated")

    canv.setFillColor(colors.HexColor("#475569"))
    canv.setFont("Helvetica", 7.6)
    canv.drawCentredString(PAGE_W / 2, 22 * mm,
                           "Built by Shreyas Kale · RVCE Bengaluru · B.E. Computer Science (Data Science)")
    canv.setFillColor(ACCENT)
    canv.rect(0, 0, PAGE_W, 6 * mm, fill=1, stroke=0)
    canv.restoreState()


# ── block -> flowable ─────────────────────────────────────────────
def _para(text, style):
    return Paragraph(text, style)


def _boxed(title, body, title_style, bg, border):
    inner = []
    if title:
        inner.append(_para(title.upper(), title_style))
    for chunk in body.split("\n\n"):
        inner.append(_para(chunk.strip(), S["box_b"]))
    t = Table([[inner]], colWidths=[BODY_W])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), bg),
        ("BOX",           (0, 0), (-1, -1), 0.6, border),
        ("LINEBEFORE",    (0, 0), (0, -1), 2.2, border),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    return [Spacer(1, 3), t, Spacer(1, 7)]


def _code(text):
    # Preformatted draws its lines verbatim -- it does NOT run the paragraph
    # XML parser -- so code blocks must be passed through unescaped. Escaping
    # here would render literal "&gt;" in comparison operators.
    inner = Preformatted(text.strip("\n"), S["code"])
    t = Table([[inner]], colWidths=[BODY_W])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), CODE_BG),
        ("BOX",           (0, 0), (-1, -1), 0.5, CODE_BR),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return [Spacer(1, 2), t, Spacer(1, 7)]


def _table(spec):
    fracs, rows = spec
    widths = [BODY_W * f for f in fracs]
    data = [[_para(str(c), S["th"]) for c in rows[0]]]
    data += [[_para(str(c), S["td"]) for c in r] for r in rows[1:]]
    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    style = [
        ("BACKGROUND",    (0, 0), (-1, 0), ACCENT),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("GRID",          (0, 0), (-1, -1), 0.4, LINE),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F8FAFC")))
    t.setStyle(TableStyle(style))
    return [Spacer(1, 3), t, Spacer(1, 8)]


ALT_HEADER = ["Option", "What it buys you", "What it costs", "Verdict"]
ALT_FRACS = [0.20, 0.30, 0.30, 0.20]


def _alts(rows):
    """Alternatives table. A row whose verdict starts with '*' is the choice
    MarketOS actually made and is highlighted."""
    data = [[_para(c, S["th"]) for c in ALT_HEADER]]
    chosen = []
    for i, r in enumerate(rows, start=1):
        verdict = r[3]
        if verdict.startswith("*"):
            chosen.append(i)
            verdict = "<b>" + verdict[1:].strip() + "</b>"
        data.append([_para(str(r[0]), S["td"]), _para(str(r[1]), S["td"]),
                     _para(str(r[2]), S["td"]), _para(verdict, S["td"])])

    t = Table(data, colWidths=[BODY_W * f for f in ALT_FRACS],
              repeatRows=1, hAlign="LEFT")
    style = [
        ("BACKGROUND",    (0, 0), (-1, 0), SLATE),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("GRID",          (0, 0), (-1, -1), 0.4, LINE),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for i in chosen:
        style += [
            ("BACKGROUND", (0, i), (-1, i), ACCENT_L),
            ("LINEBEFORE", (0, i), (0, i), 2.2, ACCENT),
        ]
    t.setStyle(TableStyle(style))
    return [Spacer(1, 3), t, Spacer(1, 8)]


def _part(payload):
    number, title, stand = payload
    return [
        PageBreak(),
        Spacer(1, 42 * mm),
        _para(f"P A R T &nbsp;&nbsp; {number}", S["part_no"]),
        HRFlowable(width="38%", thickness=1.1, color=ACCENT_B,
                   spaceBefore=5, spaceAfter=11, hAlign="CENTER"),
        _para(title, S["part_title"]),
        Spacer(1, 3),
        _para(stand, S["part_stand"]),
        PageBreak(),
    ]


def render_blocks(blocks):
    out = []
    for kind, payload in blocks:
        if kind == "part":
            out += _part(payload)
        elif kind == "h2":
            out.append(KeepTogether([
                _para(payload, S["h2"]),
                HRFlowable(width="100%", thickness=0.5, color=LINE,
                           spaceBefore=1, spaceAfter=4),
            ]))
        elif kind == "h3":
            out.append(_para(payload.upper(), S["h3"]))
        elif kind == "p":
            out.append(_para(payload, S["body"]))
        elif kind == "bul":
            out.append(ListFlowable(
                [ListItem(_para(x, S["bullet"]), leftIndent=14) for x in payload],
                bulletType="bullet", bulletFontSize=8, bulletColor=ACCENT,
                leftIndent=14, spaceBefore=2, spaceAfter=6,
            ))
        elif kind == "num":
            # Let ListFlowable do the numbering; passing an explicit `value`
            # per ListItem suppresses it and every marker renders as "1".
            out.append(ListFlowable(
                [ListItem(_para(x, S["bullet"]), leftIndent=18) for x in payload],
                bulletType="1", bulletFormat="%s.", bulletFontSize=9,
                bulletFontName="Helvetica-Bold", bulletColor=ACCENT, start=1,
                leftIndent=18, spaceBefore=2, spaceAfter=6,
            ))
        elif kind == "code":
            out += _code(payload)
        elif kind == "box":
            out += _boxed(payload[0], payload[1], S["box_t"], ACCENT_L, ACCENT_B)
        elif kind == "warn":
            out += _boxed(payload[0], payload[1], S["warn_t"], DANGER_L, DANGER_B)
        elif kind == "table":
            out += _table(payload)
        elif kind == "alts":
            out += _alts(payload)
        elif kind == "rule":
            out.append(HRFlowable(width="100%", thickness=0.5, color=LINE,
                                  spaceBefore=6, spaceAfter=6))
        elif kind == "pb":
            out.append(PageBreak())
        else:
            raise ValueError(f"unknown block kind: {kind!r}")
    return out


TOC_COLUMNS = 3


def build_toc(blocks):
    """Derives the contents page from the part/h2 blocks themselves.

    Entries are grouped by part and the groups are packed into TOC_COLUMNS
    balanced columns, breaking only at part boundaries so a part's sections
    never straddle two columns.
    """
    groups, current = [], None
    for kind, payload in blocks:
        if kind == "part":
            current = [("p", f"{payload[0]} · {payload[1]}")]
            groups.append(current)
        elif kind == "h2" and current is not None:
            current.append(("s", payload))

    total = sum(len(g) for g in groups)
    per_col = total / TOC_COLUMNS
    cols, col, used = [], [], 0
    for g in groups:
        # start a new column once this one is past its share, but never
        # leave the last column starved
        if col and used >= per_col and len(cols) < TOC_COLUMNS - 1:
            cols.append(col)
            col, used = [], 0
        for kind, txt in g:
            col.append(_para(txt, S["toc_h"] if kind == "p" else S["toc_i"]))
        used += len(g)
    cols.append(col)
    while len(cols) < TOC_COLUMNS:
        cols.append([])

    w = BODY_W / TOC_COLUMNS
    grid = Table([cols], colWidths=[w] * TOC_COLUMNS)
    grid.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (-1, 0), (-1, 0), 0),
    ]))
    # No trailing PageBreak: the first ("part", ...) block opens with one, and
    # emitting both would leave a blank page before Part 0.
    return [_para("Contents", ParagraphStyle(
        "toct", fontName="Helvetica-Bold", fontSize=17, leading=20,
        textColor=INK, spaceAfter=7)), grid]


def main(out_path="MARKETOS_BUILD_BIBLE.pdf"):
    from bible_content_a import BLOCKS as A
    from bible_content_b import BLOCKS as B
    from bible_content_c import BLOCKS as C
    from bible_content_d import BLOCKS as D
    blocks = A + B + C + D

    doc = BaseDocTemplate(
        out_path, pagesize=A4,
        leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title=DOC_TITLE, author="Shreyas Kale", subject="MarketOS engineering guide",
    )
    frame = Frame(MARGIN_L, MARGIN_B, BODY_W, PAGE_H - MARGIN_T - MARGIN_B, id="body")
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[frame], onPage=draw_cover),
        PageTemplate(id="main", frames=[frame]),
    ])

    # Page 1 is the painted cover; everything after it uses the plain "main"
    # template, so the cover art is drawn exactly once.
    story = [Spacer(1, 1), NextPageTemplate("main"), PageBreak()]
    story += build_toc(blocks)
    story += render_blocks(blocks)

    doc.build(story, canvasmaker=BibleCanvas)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "MARKETOS_BUILD_BIBLE.pdf")
