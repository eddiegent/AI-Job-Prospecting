"""Tests for the self-contained Markdown -> HTML interview-prep renderer."""
from __future__ import annotations

from scripts.md_to_html import markdown_to_html, render_interview_html


def test_headings_render_with_levels() -> None:
    html = markdown_to_html("# Title\n\n## Section\n\n### Sub")
    assert "<h1>Title</h1>" in html
    assert "<h2>Section</h2>" in html
    assert "<h3>Sub</h3>" in html


def test_horizontal_rule() -> None:
    assert "<hr>" in markdown_to_html("a\n\n---\n\nb")


def test_table_renders_thead_and_tbody() -> None:
    md = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |"
    html = markdown_to_html(md)
    assert "<table>" in html
    assert "<th>A</th><th>B</th>" in html
    assert "<td>1</td><td>2</td>" in html
    assert "<td>3</td><td>4</td>" in html
    # wrapped for horizontal scroll on narrow screens
    assert 'class="table-wrap"' in html


def test_ragged_table_row_is_padded() -> None:
    md = "| A | B |\n|---|---|\n| only-one |"
    html = markdown_to_html(md)
    assert "<td>only-one</td><td></td>" in html


def test_unordered_list() -> None:
    html = markdown_to_html("- one\n- two")
    assert "<ul>" in html and "<li>one</li>" in html and "<li>two</li>" in html


def test_ordered_list_with_continuation_line() -> None:
    # The "1. **Q** / →  answer" shape used in the interview questions section.
    md = "1. **Question ?**\n   → Answer here\n2. Second"
    html = markdown_to_html(md)
    assert "<ol>" in html
    assert "<strong>Question ?</strong><br>→ Answer here" in html
    assert "<li>Second</li>" in html


def test_inline_bold_italic_and_code() -> None:
    html = markdown_to_html("Some **bold**, *italic* and `code` here")
    assert "<strong>bold</strong>" in html
    assert "<em>italic</em>" in html
    assert "<code>code</code>" in html


def test_markdown_link() -> None:
    html = markdown_to_html("See [the offer](https://example.com/job).")
    assert '<a href="https://example.com/job">the offer</a>' in html


def test_bare_url_is_autolinked() -> None:
    html = markdown_to_html("Offre : https://www.linkedin.com/jobs/view/4251941416/")
    assert (
        '<a href="https://www.linkedin.com/jobs/view/4251941416/">'
        "https://www.linkedin.com/jobs/view/4251941416/</a>" in html
    )


def test_bare_url_trailing_punctuation_excluded() -> None:
    html = markdown_to_html("Voir https://example.com/page.")
    assert '<a href="https://example.com/page">https://example.com/page</a>.' in html


def test_html_special_chars_are_escaped() -> None:
    html = markdown_to_html("Compare C++ & C# when x < y > z")
    assert "&amp;" in html and "&lt;" in html and "&gt;" in html
    assert "<script" not in markdown_to_html("<script>alert(1)</script>")


def test_render_interview_html_is_a_full_responsive_document() -> None:
    html = render_interview_html("# Hi\n\nBody", title="Edward Gent — Acme & Co")
    assert html.startswith("<!DOCTYPE html>")
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in html
    assert "<title>Edward Gent — Acme &amp; Co</title>" in html
    assert "<style>" in html  # styling is embedded, no external assets
    assert "<h1>Hi</h1>" in html


def test_paragraph_grouping() -> None:
    html = markdown_to_html("Line one\nLine two\n\nNew para")
    assert "<p>Line one<br>Line two</p>" in html
    assert "<p>New para</p>" in html
