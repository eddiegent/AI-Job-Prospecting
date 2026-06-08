"""Self-contained Markdown -> HTML renderer for the interview-prep deliverable.

The interview prep is generated as Markdown (``_prep/interview_prep.md``) because
that's the easiest format for the model to author and for the user to edit when
re-running Step 8. The *final* deliverable, however, is an HTML file: Markdown
renders poorly in a phone/tablet text viewer, whereas a styled, responsive HTML
page reads cleanly on any device.

This module deliberately avoids a third-party Markdown dependency. The input is
*our own* controlled template (``templates/interview_prep_template_*.md`` plus
``prompts/generate_interview_prep.md``), so only a known, bounded subset of
Markdown ever reaches it:

  - ATX headings (``#`` .. ``######``)
  - horizontal rules (``---`` / ``***`` / ``___``)
  - GitHub-style pipe tables (header row + ``|---|`` separator)
  - unordered lists (``-`` / ``*`` / ``+``) and ordered lists (``1.``)
    including indented continuation lines (the "1. **Q** / →  answer" shape)
  - inline: ``**bold**``, ``*italic*``, ``[text](url)``, `` `code` ``
  - plain paragraphs

Anything outside that subset is passed through as escaped text rather than
crashing — graceful degradation, matching the PDF pipeline's philosophy.
"""
from __future__ import annotations

import html as _html
import re

__all__ = ["markdown_to_html", "render_html_document", "render_interview_html"]


_SENTINEL_CODE = "\x00C{}\x00"
_SENTINEL_LINK = "\x00L{}\x00"


def _render_inline(text: str) -> str:
    """Render inline Markdown (code, links, bold, italic) to safe HTML."""
    codes: list[str] = []
    links: list[tuple[str, str]] = []

    # Stash code spans and links BEFORE escaping so their punctuation
    # (brackets, parens, ampersands in URLs) doesn't get double-processed.
    def _stash_code(m: re.Match[str]) -> str:
        codes.append(m.group(1))
        return _SENTINEL_CODE.format(len(codes) - 1)

    def _stash_link(m: re.Match[str]) -> str:
        links.append((m.group(1), m.group(2)))
        return _SENTINEL_LINK.format(len(links) - 1)

    text = re.sub(r"`([^`]+)`", _stash_code, text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _stash_link, text)

    text = _html.escape(text, quote=False)

    # Bold first (``**``), then italic (single ``*`` not part of a ``**`` run).
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", text)

    # Auto-link bare http(s) URLs so the Quick Reference stays tappable on
    # mobile. Markdown links and code spans are already stashed as sentinels,
    # so this only touches genuinely bare URLs and never double-links.
    def _autolink(m: re.Match[str]) -> str:
        url = m.group(1)
        trail = ""
        while url and url[-1] in ".,;:)]":
            trail = url[-1] + trail
            url = url[:-1]
        return f'<a href="{url}">{url}</a>{trail}'

    text = re.sub(r"(https?://[^\s<]+)", _autolink, text)

    def _restore_link(m: re.Match[str]) -> str:
        label, url = links[int(m.group(1))]
        return (
            f'<a href="{_html.escape(url, quote=True)}">'
            f"{_html.escape(label, quote=False)}</a>"
        )

    def _restore_code(m: re.Match[str]) -> str:
        return f"<code>{_html.escape(codes[int(m.group(1))], quote=False)}</code>"

    text = re.sub(r"\x00L(\d+)\x00", _restore_link, text)
    text = re.sub(r"\x00C(\d+)\x00", _restore_code, text)
    return text


def _split_table_row(line: str) -> list[str]:
    cells = line.strip().strip("|").split("|")
    return [c.strip() for c in cells]


def _is_table_separator(line: str) -> bool:
    s = line.strip()
    if "-" not in s or not s:
        return False
    return set(s) <= set("|:- ")


def _render_table(header: str, body_lines: list[str]) -> str:
    headers = _split_table_row(header)
    out = ['<div class="table-wrap"><table>', "<thead><tr>"]
    out += [f"<th>{_render_inline(h)}</th>" for h in headers]
    out.append("</tr></thead>")
    out.append("<tbody>")
    for row in body_lines:
        cells = _split_table_row(row)
        # Pad/truncate to the header width so ragged rows don't break layout.
        cells = (cells + [""] * len(headers))[: len(headers)]
        out.append("<tr>" + "".join(f"<td>{_render_inline(c)}</td>" for c in cells) + "</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


_HEADING_RE = re.compile(r"(#{1,6})\s+(.*)")
_HR_RE = re.compile(r"(-{3,}|\*{3,}|_{3,})")
_UL_RE = re.compile(r"^\s*([-*+])\s+(.*)")
_OL_RE = re.compile(r"^\s*\d+\.\s+(.*)")


def markdown_to_html(md: str) -> str:
    """Convert the supported Markdown subset to an HTML fragment (no wrapper)."""
    lines = md.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if _HR_RE.fullmatch(stripped):
            out.append("<hr>")
            i += 1
            continue

        m = _HEADING_RE.match(stripped)
        if m:
            level = len(m.group(1))
            out.append(f"<h{level}>{_render_inline(m.group(2).strip())}</h{level}>")
            i += 1
            continue

        # Table: a row containing '|' immediately followed by a separator row.
        if "|" in line and i + 1 < n and _is_table_separator(lines[i + 1]):
            header = line
            i += 2  # consume header + separator
            body: list[str] = []
            while i < n and lines[i].strip() and "|" in lines[i]:
                body.append(lines[i])
                i += 1
            out.append(_render_table(header, body))
            continue

        # Lists (ordered / unordered) with indented continuation lines.
        if _UL_RE.match(line) or _OL_RE.match(line):
            ordered = bool(_OL_RE.match(line))
            items: list[list[str]] = []
            while i < n:
                cur = lines[i]
                mu = _UL_RE.match(cur)
                mo = _OL_RE.match(cur)
                if mu or mo:
                    items.append([(mu.group(2) if mu else mo.group(1))])
                    i += 1
                elif cur.strip() == "":
                    break
                elif re.match(r"^\s+\S", cur):  # indented continuation
                    items[-1].append(cur.strip())
                    i += 1
                else:
                    break
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>")
            for segments in items:
                rendered = "<br>".join(_render_inline(s) for s in segments)
                out.append(f"<li>{rendered}</li>")
            out.append(f"</{tag}>")
            continue

        # Paragraph: gather consecutive lines until a blank line or a new block.
        para: list[str] = []
        while i < n:
            cur = lines[i]
            cs = cur.strip()
            if not cs:
                break
            if (
                _HR_RE.fullmatch(cs)
                or _HEADING_RE.match(cs)
                or _UL_RE.match(cur)
                or _OL_RE.match(cur)
                or ("|" in cur and i + 1 < n and _is_table_separator(lines[i + 1]))
            ):
                break
            para.append(cs)
            i += 1
        out.append("<p>" + "<br>".join(_render_inline(p) for p in para) + "</p>")

    return "\n".join(out)


_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.6;
  color: #1b1f24;
  background: #ffffff;
  margin: 0;
  padding: 1.25rem 1rem 4rem;
  -webkit-text-size-adjust: 100%;
}
.container { max-width: 820px; margin: 0 auto; }
h1 { font-size: 1.6rem; line-height: 1.25; margin: 1.4rem 0 0.6rem; }
h2 { font-size: 1.25rem; margin: 1.8rem 0 0.5rem; padding-bottom: 0.25rem; border-bottom: 2px solid #e6e8eb; }
h3 { font-size: 1.05rem; margin: 1.3rem 0 0.4rem; }
p { margin: 0.6rem 0; }
a { color: #0969da; word-break: break-word; }
hr { border: 0; border-top: 1px solid #e6e8eb; margin: 1.4rem 0; }
ul, ol { padding-left: 1.4rem; margin: 0.6rem 0; }
li { margin: 0.35rem 0; }
code {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  background: #f0f2f4; padding: 0.1rem 0.35rem; border-radius: 5px; font-size: 0.9em;
}
.table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; margin: 0.8rem 0; }
table { border-collapse: collapse; width: 100%; font-size: 0.95rem; }
th, td { border: 1px solid #d8dce0; padding: 0.5rem 0.7rem; text-align: left; vertical-align: top; }
th { background: #f6f8fa; font-weight: 600; }
tr:nth-child(even) td { background: #fbfcfd; }
@media (prefers-color-scheme: dark) {
  body { color: #e6e8eb; background: #15181c; }
  h2 { border-bottom-color: #2a2f36; }
  hr { border-top-color: #2a2f36; }
  a { color: #5aa7ff; }
  code { background: #23272e; }
  th { background: #1d2127; }
  th, td { border-color: #2a2f36; }
  tr:nth-child(even) td { background: #1a1e23; }
}
""".strip()


def render_html_document(md: str, title: str, lang: str = "fr") -> str:
    """Wrap converted Markdown in a complete, responsive HTML document.

    Used for any candidate-facing Markdown deliverable that benefits from
    clean mobile/tablet rendering — the offer flow's interview prep and the
    cold flow's company dossier both go through here.
    """
    body = markdown_to_html(md)
    safe_title = _html.escape(title, quote=False)
    safe_lang = _html.escape(lang, quote=True) or "fr"
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="{safe_lang}">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{safe_title}</title>\n"
        f"<style>\n{_CSS}\n</style>\n"
        "</head>\n<body>\n"
        f'<div class="container">\n{body}\n</div>\n'
        "</body>\n</html>\n"
    )


def render_interview_html(md: str, title: str) -> str:
    """Backwards-compatible alias — renders an interview-prep HTML document."""
    return render_html_document(md, title)
