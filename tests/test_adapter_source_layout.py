"""Automatic inline ranges use original source coordinates."""

import pytest

from doc_lingo.documents import TextSegment
from doc_lingo.documents.html_text import HtmlSegment, HtmlText
from doc_lingo.documents.markdown import MarkdownReader, MarkdownWriter
from doc_lingo.documents.markdown_layout import inline_source_layout


@pytest.mark.parametrize(
    "source,expected",
    [
        ("The **model** works.", "The model works."),
        ("***nested*** and ~~old~~", "nested and old"),
        ("**outer *inner* end**", "outer inner end"),
        ('[the **guide**](/url "Title")', "the guide"),
        ("**same** same *same*", "same same same"),
        (r"\*literal\* and *real*", r"\*literal\* and real"),
        ("unmatched **word", "unmatched **word"),
        ("`**code**` and **text**", "`**code**` and text"),
        ("![**image**](/img) and *text*", "![**image**](/img) and text"),
        ("<strong>**text**</strong>", "text"),
        ('<span title="**attribute**">*text*</span>', "text"),
        ('<span translate="no">**keep**</span> *yes*', '<span translate="no">**keep**</span> yes'),
        ("<code>**keep**</code> *yes*", "<code>**keep**</code> yes"),
        ("**a <em>b** c</em>", "**a <em>b** c</em>"),
        ("Text <!-- **comment** --> *yes*", "Text <!-- **comment** --> yes"),
    ],
)
def test_markdown_segment_layout(tmp_path, source, expected):
    path = tmp_path / "source.md"
    path.write_text(source, encoding="utf-8")
    with MarkdownReader(path).iter_segments() as segments:
        segment = next(segments)
        layout = segment.source_layout()
    assert layout.source == segment.text
    assert layout.extract_text() == expected
    assert segment.text == source


def test_reference_link_uses_document_environment(tmp_path):
    path = tmp_path / "source.md"
    path.write_text("[**guide**][ref]\n\n[ref]: /url\n", encoding="utf-8")
    with MarkdownReader(path).iter_segments() as segments:
        layout = next(segments).source_layout()
    assert layout.extract_text().strip() == "guide"


def test_implicit_reference_label_stays_opaque(tmp_path):
    path = tmp_path / "source.md"
    path.write_text("Read [**guide**][]\n\n[**guide**]: /url\n", encoding="utf-8")
    with MarkdownReader(path).iter_segments() as segments:
        segment = next(segments)
        assert segment.source_layout().extract_text() == segment.text


@pytest.mark.parametrize(
    "source",
    ["<b>x</i> *yes*", "[**guide**][]\n\n[**guide**]: /url\n"],
)
def test_fully_retained_source_has_no_translation_segments(tmp_path, source):
    path = tmp_path / "source.md"
    path.write_bytes(source.encode("utf-8"))
    with MarkdownReader(path).iter_segments() as segments:
        assert list(segments) == []
    destination = tmp_path / "output.md"
    MarkdownWriter(path).write(destination, [])
    assert destination.read_bytes() == path.read_bytes()


def test_inline_layout_retains_unsafe_html():
    source = "<b>x</i> *yes*"
    layout = inline_source_layout(source, {}, HtmlText(source))
    assert layout.ranges == ()
    assert layout.extract_text() == source


def test_html_ranges_keep_attributes_in_original():
    source = '<b class="x">ä<i>😀</i></b>'
    layout = HtmlSegment("1", source).source_layout()
    assert layout.extract_text() == "ä😀"
    outer, inner = layout.ranges
    assert source[outer.outer_start : outer.inner_start] == '<b class="x">'
    assert source[inner.inner_start : inner.inner_end] == "😀"


@pytest.mark.parametrize("source", ["<b>open", "<b>x</i>", "<code><b>x</b></code>", "<!--x-->"])
def test_incomplete_excluded_or_noncontainer_html_is_retained(source):
    assert HtmlText(source).source_layout().extract_text() == source


def test_plain_segment_has_no_wrappers():
    assert TextSegment("1", "**literal**").source_layout().extract_text() == "**literal**"
