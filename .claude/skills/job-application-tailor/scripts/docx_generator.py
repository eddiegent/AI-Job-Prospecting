from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.shared import Pt, Inches, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from common import ensure_dir, load_yaml

SKILL_ROOT = Path(__file__).resolve().parent.parent


def _require(data: dict, field: str, context: str) -> Any:
    """Return data[field] or exit with a clear error."""
    if field not in data or not data[field]:
        print(f"ERROR in {context}: required field '{field}' is missing or empty.", file=sys.stderr)
        sys.exit(1)
    return data[field]


def _set_font(style, font_name: str) -> None:
    """Set font name including East Asia fallback."""
    style.font.name = font_name
    style._element.rPr.rFonts.set(qn("w:eastAsia"), font_name)


def _set_default_font(document: Document, font_name: str, body_size_pt: int) -> None:
    styles = document.styles
    normal = styles["Normal"]
    _set_font(normal, font_name)
    normal.font.size = Pt(body_size_pt)

    # Matching master CV styles: NameStyle, TaglineStyle, SectionStyle, RoleStyle, CompanyStyle, SubtleStyle
    existing = {s.name for s in styles}

    if "NameStyle" not in existing:
        s = styles.add_style("NameStyle", WD_STYLE_TYPE.PARAGRAPH)
        s.base_style = normal
        _set_font(s, font_name)
        s.font.size = Pt(19)
        s.font.bold = True
        s.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)

    if "TaglineStyle" not in existing:
        s = styles.add_style("TaglineStyle", WD_STYLE_TYPE.PARAGRAPH)
        s.base_style = normal
        _set_font(s, font_name)
        s.font.size = Pt(11.5)
        s.font.bold = True
        s.font.color.rgb = RGBColor(0x44, 0x44, 0x44)

    if "SectionStyle" not in existing:
        s = styles.add_style("SectionStyle", WD_STYLE_TYPE.PARAGRAPH)
        s.base_style = normal
        _set_font(s, font_name)
        s.font.size = Pt(12)
        s.font.bold = True
        s.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)

    if "RoleStyle" not in existing:
        s = styles.add_style("RoleStyle", WD_STYLE_TYPE.PARAGRAPH)
        s.base_style = normal
        _set_font(s, font_name)
        s.font.size = Pt(11.5)
        s.font.bold = True
        s.font.color.rgb = RGBColor(0x00, 0x00, 0x00)

    if "CompanyStyle" not in existing:
        s = styles.add_style("CompanyStyle", WD_STYLE_TYPE.PARAGRAPH)
        s.base_style = normal
        _set_font(s, font_name)
        s.font.bold = True
        s.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)

    if "SubtleStyle" not in existing:
        s = styles.add_style("SubtleStyle", WD_STYLE_TYPE.PARAGRAPH)
        s.base_style = normal
        _set_font(s, font_name)
        s.font.size = Pt(9.5)
        s.font.italic = True
        s.font.color.rgb = RGBColor(0x60, 0x60, 0x60)

    # Keep legacy SkillHeading/RoleHeader as aliases
    if "SkillHeading" not in existing:
        heading = styles.add_style("SkillHeading", WD_STYLE_TYPE.PARAGRAPH)
        heading.base_style = styles["SectionStyle"]

    if "RoleHeader" not in existing:
        role = styles.add_style("RoleHeader", WD_STYLE_TYPE.PARAGRAPH)
        role.base_style = styles["RoleStyle"]


def _set_margins(document: Document) -> None:
    section = document.sections[0]
    section.top_margin = Inches(0.65)
    section.bottom_margin = Inches(0.65)
    section.left_margin = Inches(0.75)
    section.right_margin = Inches(0.75)


def _add_title(document: Document, text: str, font_name: str, size_pt: int) -> None:
    p = document.add_paragraph(style="NameStyle")
    p.add_run(text)
    p.space_after = Pt(2)


def _add_plain(document: Document, text: str, bold: bool = False) -> None:
    p = document.add_paragraph()
    run = p.add_run(text)
    run.bold = bold


def _add_hyperlink(paragraph, url: str, text: str) -> None:
    """Add a clickable hyperlink to a paragraph."""
    part = paragraph.part
    r_id = part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)

    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)

    new_run = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")

    color = OxmlElement("w:color")
    color.set(qn("w:val"), "0563C1")
    rPr.append(color)

    u = OxmlElement("w:u")
    u.set(qn("w:val"), "single")
    rPr.append(u)

    new_run.append(rPr)
    new_run.text = text
    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)


def _add_contact_line_with_links(document: Document, contact_line: str) -> None:
    """Parse the contact line and make emails/URLs clickable."""
    p = document.add_paragraph()

    email_re = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
    url_re = re.compile(r'(?:https?://)?(?:www\.)?linkedin\.com/\S+|(?:https?://)\S+')

    parts = re.split(r'(\s*\|\s*)', contact_line)
    for part in parts:
        email_match = email_re.search(part)
        url_match = url_re.search(part)
        if email_match:
            email = email_match.group()
            _add_hyperlink(p, f"mailto:{email}", email)
        elif url_match:
            url = url_match.group()
            href = url if url.startswith("http") else f"https://{url}"
            _add_hyperlink(p, href, url)
        else:
            p.add_run(part)


def _add_heading(document: Document, text: str) -> None:
    p = document.add_paragraph(style="SkillHeading")
    p.add_run(text)


def _add_bullets(document: Document, items: list[str]) -> None:
    for item in items:
        p = document.add_paragraph(style="List Bullet")
        p.add_run(item)


def _load_section_labels(language: str) -> dict[str, str]:
    lang_file = SKILL_ROOT / "config" / "languages.yaml"
    if lang_file.exists():
        langs = load_yaml(lang_file)
        lang_data = langs.get(language, langs.get("fr", {}))
        return lang_data.get("cv_sections", {})
    return {}


_DEFAULT_LABELS = {
    "profile": "Profil professionnel",
    "skills": "Compétences",
    "experience": "Expérience professionnelle",
    "education": "Formation",
    "languages": "Langues",
}


def generate_cv_docx(output_path: Path, cv_data: dict[str, Any], settings: dict[str, Any], language: str = "fr") -> Path:
    _require(cv_data, "candidate_name", "CV DOCX")
    _require(cv_data, "experience", "CV DOCX")
    _require(settings, "formatting", "settings")

    ensure_dir(output_path.parent)
    formatting = settings["formatting"]
    labels = {**_DEFAULT_LABELS, **_load_section_labels(language)}
    doc = Document()
    _set_margins(doc)
    _set_default_font(doc, formatting["font_name"], formatting["body_font_size_pt"])

    # Name
    _add_title(doc, cv_data.get("candidate_name", ""), formatting["font_name"], formatting["title_font_size_pt"])

    # Title / tagline
    title = cv_data.get("title", "")
    if title:
        doc.add_paragraph(title, style="TaglineStyle")
    tagline = cv_data.get("tagline", "")
    if tagline:
        doc.add_paragraph(tagline, style="TaglineStyle")

    # Contact line with clickable links
    contact_line = cv_data.get("contact_line", "")
    if contact_line:
        _add_contact_line_with_links(doc, contact_line)

    # Profile summary
    doc.add_paragraph(labels["profile"], style="SectionStyle")
    for para in cv_data.get("summary_paragraphs", []):
        doc.add_paragraph(para)

    # Skills
    doc.add_paragraph(labels["skills"], style="SectionStyle")
    for section in cv_data.get("skills_sections", []):
        heading = section.get("heading", "")
        items = section.get("items", [])
        if heading:
            p = doc.add_paragraph()
            r = p.add_run(f"{heading} : ")
            r.bold = True
            p.add_run(", ".join(items))

    # Experience
    doc.add_paragraph(labels["experience"], style="SectionStyle")
    for role in cv_data.get("experience", []):
        # Role title
        doc.add_paragraph(role.get("company_role_line", ""), style="RoleStyle")
        # Date line
        date_line = role.get("date_line", "")
        if date_line:
            doc.add_paragraph(date_line, style="SubtleStyle")
        _add_bullets(doc, role.get("bullets", []))

    # Education
    if cv_data.get("education"):
        doc.add_paragraph(labels["education"], style="SectionStyle")
        for line in cv_data["education"]:
            doc.add_paragraph(line)

    # Languages
    if cv_data.get("languages"):
        doc.add_paragraph(labels["languages"], style="SectionStyle")
        doc.add_paragraph(", ".join(cv_data["languages"]))

    doc.save(str(output_path))
    return output_path


def generate_letter_docx(output_path: Path, letter_data: dict[str, Any], settings: dict[str, Any]) -> Path:
    _require(letter_data, "paragraphs", "Letter DOCX")
    _require(letter_data, "name", "Letter DOCX")
    _require(settings, "formatting", "settings")

    ensure_dir(output_path.parent)
    formatting = settings["formatting"]
    doc = Document()
    _set_margins(doc)
    _set_default_font(doc, formatting["font_name"], formatting["body_font_size_pt"])

    # Sender block (top-left)
    if letter_data.get("sender_name") or letter_data.get("sender_address"):
        if letter_data.get("sender_name"):
            p = doc.add_paragraph()
            r = p.add_run(letter_data["sender_name"])
            r.bold = True
        for line in letter_data.get("sender_address", []):
            doc.add_paragraph(line)
        doc.add_paragraph("")  # spacing

    # Recipient block
    if letter_data.get("recipient_name") or letter_data.get("recipient_address"):
        if letter_data.get("recipient_name"):
            p = doc.add_paragraph()
            r = p.add_run(letter_data["recipient_name"])
            r.bold = True
        for line in letter_data.get("recipient_address", []):
            doc.add_paragraph(line)
        doc.add_paragraph("")  # spacing

    if letter_data.get("date_line"):
        doc.add_paragraph(letter_data["date_line"])
    if letter_data.get("subject_line"):
        p = doc.add_paragraph()
        r = p.add_run(letter_data["subject_line"])
        r.bold = True
    if letter_data.get("greeting"):
        doc.add_paragraph(letter_data["greeting"])
    for para in letter_data.get("paragraphs", []):
        doc.add_paragraph(para)
    signoff = letter_data.get("signoff", "")
    name = letter_data.get("name", "")
    if signoff:
        doc.add_paragraph(signoff)
    if name:
        doc.add_paragraph(name)

    doc.save(str(output_path))
    return output_path
