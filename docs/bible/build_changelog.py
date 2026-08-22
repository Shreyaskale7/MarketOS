# build_changelog.py
# Standalone renderer for MARKETOS_CHANGELOG.pdf — reuses build_bible.py's
# styles, block-dispatcher and canvas (BibleCanvas) so the changelog is
# visually consistent with the bible, but is its own document with its own
# cover, table of contents and content file (changelog_content.py).

import sys
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Spacer, PageBreak, NextPageTemplate

from build_bible import (
    S, BODY_W, PAGE_W, PAGE_H, MARGIN_L, MARGIN_R, MARGIN_T, MARGIN_B,
    ACCENT, ACCENT_B, BibleCanvas, render_blocks, build_toc,
    _para,
)

DOC_TITLE = "MarketOS — Deployment & Correctness Change Log"
COVER_BG = colors.HexColor("#071019")


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
                           "A   S U P P L E M E N T   T O   T H E   B U I L D   B I B L E")

    canv.setFillColor(colors.white)
    canv.setFont("Helvetica-Bold", 38)
    canv.drawCentredString(PAGE_W / 2, PAGE_H - 88 * mm, "MarketOS")
    canv.setFont("Helvetica", 16)
    canv.setFillColor(colors.HexColor("#CBD5E1"))
    canv.drawCentredString(PAGE_W / 2, PAGE_H - 100 * mm, "Deployment & Correctness Change Log")

    canv.setStrokeColor(colors.HexColor("#155E75"))
    canv.setLineWidth(0.8)
    canv.line(45 * mm, PAGE_H - 109 * mm, PAGE_W - 45 * mm, PAGE_H - 109 * mm)

    canv.setFont("Helvetica", 9.6)
    canv.setFillColor(colors.HexColor("#94A3B8"))
    for i, line in enumerate([
        "Everything found and fixed while taking MarketOS from a local build to a",
        "live, automated deployment — every entry cross-references the section of",
        "THE COMPLETE BUILD BIBLE it changes, updates, or corrects, and states",
        "why the change was made, not just what changed.",
    ]):
        canv.drawCentredString(PAGE_W / 2, PAGE_H - (119 + i * 5.6) * mm, line)

    canv.setFont("Helvetica", 8.4)
    canv.setFillColor(colors.HexColor("#67E8F9"))
    canv.drawCentredString(
        PAGE_W / 2, PAGE_H - 152 * mm,
        "9 correctness bugs found and fixed · deployment stabilised · daily run automated")
    canv.setFillColor(colors.HexColor("#64748B"))
    canv.setFont("Helvetica", 8)
    canv.drawCentredString(
        PAGE_W / 2, PAGE_H - 159 * mm,
        "Read together with MARKETOS_BUILD_BIBLE.pdf — this document assumes it as context")

    canv.setFillColor(colors.HexColor("#475569"))
    canv.setFont("Helvetica", 7.6)
    canv.drawCentredString(PAGE_W / 2, 22 * mm,
                           "Shreyas Kale · RVCE Bengaluru · B.E. Computer Science (Data Science)")
    canv.setFillColor(ACCENT)
    canv.rect(0, 0, PAGE_W, 6 * mm, fill=1, stroke=0)
    canv.restoreState()


def main(out_path="MARKETOS_CHANGELOG.pdf"):
    from changelog_content import BLOCKS

    doc = BaseDocTemplate(
        out_path, pagesize=A4,
        leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title=DOC_TITLE, author="Shreyas Kale",
        subject="MarketOS deployment and correctness change log",
    )
    frame = Frame(MARGIN_L, MARGIN_B, BODY_W, PAGE_H - MARGIN_T - MARGIN_B, id="body")
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[frame], onPage=draw_cover),
        PageTemplate(id="main", frames=[frame]),
    ])

    # build_bible's DOC_TITLE (used in the running header) is module-level;
    # point it at THIS document's title before rendering.
    import build_bible
    build_bible.DOC_TITLE = DOC_TITLE

    story = [Spacer(1, 1), NextPageTemplate("main"), PageBreak()]
    story += build_toc(BLOCKS)
    story += render_blocks(BLOCKS)

    doc.build(story, canvasmaker=BibleCanvas)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "MARKETOS_CHANGELOG.pdf")
