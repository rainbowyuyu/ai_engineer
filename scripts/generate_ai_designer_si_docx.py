#!/usr/bin/env python3
"""Regenerate AI Designer r2 Supplementary Information DOCX.

Matches Nature-format manuscript styling from ``0728-AI designer-r2.docx``:
Unicode math (not raw LaTeX), real Word tables, A4 margins, Heading 1/2 sizes.
"""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

REPO = Path(__file__).resolve().parents[1]
MD_SRC = REPO / "docs" / "AI_Designer_r2_Supplementary_Information.md"
OUT = REPO / "docs" / "AI_Designer_r2_Supplementary_Information.docx"
OUT_FALLBACK = REPO / "docs" / "AI_Designer_r2_Supplementary_Information_fixed.docx"
MAIN_TEMPLATE = Path(
    r"c:\Users\zju\Documents\xwechat_files\wxid_jdc2tzsjmvqc12_b63e\msg\file\2026-07\0728-AI designer-r2.docx"
)

_SUB = str.maketrans(
    "0123456789aehijklmnoprstuvx+-=()",
    "₀₁₂₃₄₅₆₇₈₉ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ₊₋₌₍₎",
)
_SUP = str.maketrans("0123456789+-=()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾")


def _sub(s: str) -> str:
    out = s.translate(_SUB)
    # if any char lacked a unicode subscript, keep underscore form
    if out == s and not s.isdigit():
        return "_" + s
    return out


def _sup(s: str) -> str:
    out = s.translate(_SUP)
    if out == s and not all(ch.isdigit() or ch in "+-" for ch in s):
        return "^" + s
    return out


def _latex_inner(s: str) -> str:
    s = s.strip()
    # 5^\circ before bare \circ
    s = re.sub(r"\^\{?\\circ\}?|\^\\circ", "°", s)
    s = re.sub(r"\\mathrm\{([^{}]+)\}", r"\1", s)
    s = re.sub(r"\\mathbf\{([^{}]+)\}", r"\1", s)
    s = re.sub(r"\\text\{([^{}]+)\}", r"\1", s)
    s = re.sub(r"\\operatorname\{([^{}]+)\}", r"\1", s)
    s = re.sub(r"\\qquad|\\quad", "  ", s)
    s = s.replace(r"\,", " ").replace(r"\;", " ").replace(r"\!", "")

    greek = {
        r"\rho": "ρ",
        r"\theta": "θ",
        r"\tau": "τ",
        r"\omega": "ω",
        r"\Omega": "Ω",
        r"\Delta": "Δ",
        r"\delta": "δ",
        r"\phi": "φ",
        r"\psi": "ψ",
        r"\alpha": "α",
        r"\beta": "β",
        r"\gamma": "γ",
        r"\sigma": "σ",
        r"\Sigma": "Σ",
        r"\pi": "π",
        r"\epsilon": "ε",
        r"\ge": "≥",
        r"\le": "≤",
        r"\leq": "≤",
        r"\geq": "≥",
        r"\neq": "≠",
        r"\approx": "≈",
        r"\times": "×",
        r"\cdot": "·",
        r"\ldots": "…",
        r"\dots": "…",
        r"\infty": "∞",
        r"\in": "∈",
        r"\subset": "⊂",
        r"\rightarrow": "→",
        r"\leftarrow": "←",
        r"\Rightarrow": "⇒",
        r"\leftrightarrow": "↔",
        r"\exists": "∃",
        r"\forall": "∀",
        r"\min": "min",
        r"\max": "max",
        r"\sum": "Σ",
        r"\prod": "Π",
        r"\sqrt": "√",
        r"\circ": "°",
        r"\ ": " ",
        r"\{": "{",
        r"\}": "}",
        r"\%": "%",
        r"\_": "_",
    }
    for k in sorted(greek.keys(), key=len, reverse=True):
        s = s.replace(k, greek[k])

    def sub_cb(m: re.Match[str]) -> str:
        body = m.group(1).replace("\\", "").strip()
        if body.isdigit() or (len(body) == 1 and body.isalnum()):
            return _sub(body)
        # multi-letter → m_goal / P_target (main-manuscript style)
        return "_" + body

    def sup_cb(m: re.Match[str]) -> str:
        body = m.group(1).replace("\\", "").strip()
        if body in ("circ", "o", "°"):
            return "°"
        if body in ("*", "ast"):
            return "*"
        if re.fullmatch(r"-\d+", body):
            return "⁻" + _sup(body[1:])
        if body.isdigit():
            return _sup(body)
        return "^" + body

    s = re.sub(r"\^\{([^{}]+)\}", sup_cb, s)
    s = re.sub(r"_\{([^{}]+)\}", sub_cb, s)
    s = re.sub(
        r"\^(-?\d+)",
        lambda m: ("⁻" + _sup(m.group(1)[1:])) if m.group(1).startswith("-") else _sup(m.group(1)),
        s,
    )
    s = re.sub(r"\^\*", "*", s)
    # single-char / digit subscript only when not start of a longer name (_goal)
    s = re.sub(r"_([0-9a-zA-Z])(?![A-Za-z0-9])", lambda m: _sub(m.group(1)), s)

    s = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"(\1)/(\2)", s)
    s = re.sub(r"√\{([^{}]+)\}", r"√(\1)", s)
    s = re.sub(r"\\bigl|\\bigr|\\Bigl|\\Bigr|\\left|\\right", "", s)
    s = re.sub(r"\\([A-Za-z]+)", r"\1", s)
    # keep set braces { }; drop only empty remnants
    s = re.sub(r"\{\s*\}", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def latex_to_plain(text: str) -> str:
    if not text:
        return text

    def repl_math(m: re.Match[str]) -> str:
        return _latex_inner(m.group(1))

    text = re.sub(r"\$\$(.+?)\$\$", repl_math, text, flags=re.S)
    text = re.sub(r"\\\[(.+?)\\\]", repl_math, text, flags=re.S)
    text = re.sub(r"\\\((.+?)\\\)", repl_math, text, flags=re.S)
    text = re.sub(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)", repl_math, text, flags=re.S)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", text)
    text = text.replace("&nbsp;", " ").replace("\u00a0", " ")
    # equation lines without \( \): still full convert
    if re.search(r"\\[A-Za-z]|\\sum|\\frac|\\mathrm|\\times|\\le|\\ge|\\sqrt|\\cdot|\\qquad", text):
        text = _latex_inner(text)
    return text.strip()


def set_run_font(run, *, size: float = 10.5, bold: bool = False, italic: bool = False) -> None:
    run.font.name = "Times New Roman"
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    rfonts.set(qn("w:ascii"), "Times New Roman")
    rfonts.set(qn("w:hAnsi"), "Times New Roman")
    rfonts.set(qn("w:eastAsia"), "Times New Roman")
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    run.font.color.rgb = RGBColor(0, 0, 0)


def add_para(
    doc: Document,
    text: str,
    *,
    size: float = 10.5,
    bold: bool = False,
    italic: bool = False,
    space_after: float = 8,
) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    run = p.add_run(latex_to_plain(text))
    set_run_font(run, size=size, bold=bold, italic=italic)


def add_heading_styled(doc: Document, text: str, level: int) -> None:
    p = doc.add_heading(level=level)
    p.clear()
    run = p.add_run(latex_to_plain(text))
    if level == 1:
        set_run_font(run, size=16, bold=True)
        p.paragraph_format.space_before = Pt(18)
        p.paragraph_format.space_after = Pt(8)
    else:
        set_run_font(run, size=15, bold=True)
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.space_after = Pt(6)


def add_table(doc: Document, headers: list[str], rows: list[list[str]], *, caption: str | None = None) -> None:
    if caption:
        add_para(doc, caption, bold=True, size=10, space_after=4)
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    table.autofit = True
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        run = p.add_run(latex_to_plain(h))
        set_run_font(run, size=9.5, bold=True)
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()
        shd = tcPr.makeelement(
            qn("w:shd"),
            {qn("w:val"): "clear", qn("w:color"): "auto", qn("w:fill"): "EEF2F7"},
        )
        tcPr.append(shd)
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            cell = table.rows[ri + 1].cells[ci]
            cell.text = ""
            p = cell.paragraphs[0]
            run = p.add_run(latex_to_plain(str(val)))
            set_run_font(run, size=9.5)
    doc.add_paragraph().paragraph_format.space_after = Pt(6)


def add_equation(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run(latex_to_plain(text))
    set_run_font(run, size=10.5)


def add_bullet(doc: Document, text: str) -> None:
    p = doc.add_paragraph(style="List Bullet")
    p.clear()
    p.paragraph_format.space_after = Pt(3)
    run = p.add_run(latex_to_plain(text))
    set_run_font(run, size=10.5)


def parse_md_table(lines: list[str], start: int) -> tuple[list[str], list[list[str]], int]:
    header = [c.strip() for c in lines[start].strip().strip("|").split("|")]
    i = start + 1
    if i < len(lines) and re.match(r"^\s*\|?\s*:?-+:?\s*\|", lines[i]):
        i += 1
    rows: list[list[str]] = []
    while i < len(lines) and lines[i].strip().startswith("|"):
        row = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        if len(row) < len(header):
            row += [""] * (len(header) - len(row))
        rows.append(row[: len(header)])
        i += 1
    return header, rows, i


def apply_page_setup(doc: Document) -> None:
    sec = doc.sections[0]
    if MAIN_TEMPLATE.is_file():
        main = Document(str(MAIN_TEMPLATE))
        m = main.sections[0]
        sec.page_width = m.page_width
        sec.page_height = m.page_height
        sec.left_margin = m.left_margin
        sec.right_margin = m.right_margin
        sec.top_margin = m.top_margin
        sec.bottom_margin = m.bottom_margin
    else:
        sec.page_width = Inches(8.27)
        sec.page_height = Inches(11.69)
        sec.left_margin = Inches(1.25)
        sec.right_margin = Inches(1.25)
        sec.top_margin = Inches(1.0)
        sec.bottom_margin = Inches(1.0)


def build() -> Path:
    lines = MD_SRC.read_text(encoding="utf-8").splitlines()
    doc = Document()
    apply_page_setup(doc)

    try:
        normal = doc.styles["Normal"]
        normal.font.name = "Times New Roman"
        normal.font.size = Pt(10.5)
        normal._element.rPr.rFonts.set(qn("w:ascii"), "Times New Roman")
        normal._element.rPr.rFonts.set(qn("w:hAnsi"), "Times New Roman")
    except Exception:
        pass

    i = 0
    pending_caption: str | None = None
    while i < len(lines):
        stripped = lines[i].strip()

        if not stripped or stripped == "---":
            i += 1
            continue

        if stripped.startswith("# ") and not stripped.startswith("## "):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(12)
            run = p.add_run(latex_to_plain(stripped[2:].strip()))
            set_run_font(run, size=18, bold=True)
            i += 1
            continue

        if stripped.startswith("## "):
            add_heading_styled(doc, stripped[3:].strip(), 1)
            i += 1
            continue

        if stripped.startswith("### "):
            # Table captions under ### Table ...
            if stripped.lower().startswith("### table"):
                pending_caption = latex_to_plain(stripped[4:].strip())
                i += 1
                continue
            add_heading_styled(doc, stripped[4:].strip(), 2)
            i += 1
            continue

        if stripped.startswith("|") and i + 1 < len(lines) and re.search(r"\|?\s*-{3,}", lines[i + 1]):
            headers, rows, ni = parse_md_table(lines, i)
            add_table(doc, headers, rows, caption=pending_caption)
            pending_caption = None
            i = ni
            continue

        if stripped.startswith("\\[") or stripped.startswith("$$"):
            buf = [stripped]
            i += 1
            while i < len(lines):
                buf.append(lines[i].rstrip())
                if "\\]" in lines[i] or lines[i].strip().endswith("$$"):
                    i += 1
                    break
                i += 1
            block = "\n".join(buf).replace("\\[", "").replace("\\]", "").replace("$$", "")
            add_equation(doc, block)
            continue

        if stripped.startswith("- "):
            add_bullet(doc, stripped[2:])
            i += 1
            continue

        if re.match(r"^\d+\.\s", stripped):
            add_bullet(doc, stripped)
            i += 1
            continue

        if stripped.startswith("*") and stripped.endswith("*") and not stripped.startswith("**"):
            add_para(doc, stripped.strip("*"), italic=True, size=10)
            i += 1
            continue

        para_lines = [stripped]
        i += 1
        while i < len(lines):
            ns = lines[i].strip()
            if not ns:
                break
            if ns.startswith("#") or ns.startswith("|") or ns.startswith("- ") or ns == "---":
                break
            if ns.startswith("\\[") or ns.startswith("$$"):
                break
            if re.match(r"^\d+\.\s", ns):
                break
            para_lines.append(ns)
            i += 1
        add_para(doc, " ".join(para_lines), space_after=8)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    try:
        doc.save(str(OUT))
        return OUT
    except PermissionError:
        doc.save(str(OUT_FALLBACK))
        return OUT_FALLBACK


if __name__ == "__main__":
    path = build()
    d = Document(str(path))
    print(f"Wrote {path}")
    print(f"paragraphs={len(d.paragraphs)} tables={len(d.tables)}")
    bad = 0
    for t in d.tables:
        for row in t.rows:
            for c in row.cells:
                if "\\(" in c.text or "mathrm" in c.text or "|---" in c.text:
                    bad += 1
                    print("BAD:", repr(c.text[:100]))
    print(f"bad_cells={bad}")
    if d.tables:
        print("table0 header:", [c.text for c in d.tables[0].rows[0].cells])
        print("table0 row1:", [c.text for c in d.tables[0].rows[1].cells])
