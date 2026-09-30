"""Input preparation preserves source identity and opaque content."""

import pytest

from doc_lingo.documents import SourceLayout, SourceRange, TextSegment, TranslationInput
from doc_lingo.documents.markdown import MarkdownReader


@pytest.mark.parametrize("source", ["", "plain", "😀\r\n ä\t"])
def test_plain_input_is_lossless(source):
    prepared = TextSegment("1", source).translation_input()
    assert prepared.text == source
    assert all(part.kind == "text" for part in prepared.parts)
    assert "".join(source[p.start : p.end] for p in prepared.parts) == source


def test_protected_content_is_distinct_from_removable_syntax():
    source = "**word** code"
    layout = SourceLayout(source, (SourceRange(0, 2, 6, 8),))
    prepared = TranslationInput.from_layout(layout, ((0, 2), (6, 8), (9, 13)))
    assert prepared.text == "word code"
    assert [(p.kind, source[p.start : p.end]) for p in prepared.parts] == [
        ("syntax", "**"),
        ("text", "word"),
        ("syntax", "**"),
        ("text", " "),
        ("protected", "code"),
    ]


def test_nested_formatting_across_sentences_keeps_original_relationship():
    source = "**First. *Second.* Third.**"
    layout = SourceLayout(source, (SourceRange(0, 2, 25, 27), SourceRange(9, 10, 17, 18)))
    prepared = TranslationInput.from_layout(layout)
    assert prepared.text == "First. Second. Third."
    assert prepared.layout is layout
    assert "".join(source[p.start : p.end] for p in prepared.parts) == source


def test_adjacent_protection_and_empty_wrappers():
    prepared = TranslationInput.from_layout(SourceLayout("abcd"), ((0, 2), (2, 4)))
    assert len(prepared.parts) == 1
    assert prepared.parts[0].kind == "protected"
    assert prepared.text == "abcd"
    assert TranslationInput.from_layout(SourceLayout("x", (SourceRange(0, 0, 1, 1),))).text == "x"
    assert TranslationInput.from_layout(SourceLayout("**", (SourceRange(0, 1, 1, 2),))).text == ""


@pytest.mark.parametrize("spans", [((-1, 1),), ((1, 1),), ((0, 5),), ((0, 2), (1, 3))])
def test_invalid_protected_ranges(spans):
    with pytest.raises(ValueError, match="Invalid protected input range"):
        TranslationInput.from_layout(SourceLayout("text"), spans)


def test_markdown_input_retains_code_and_link_context(tmp_path):
    source = 'Read [**the guide**](/url "Title") and keep `a()`.'
    path = tmp_path / "source.md"
    path.write_text(source, encoding="utf-8")
    with MarkdownReader(path).iter_segments() as segments:
        segment = next(segments)
        prepared = segment.translation_input()
    assert prepared.text == "Read the guide and keep `a()`."
    protected = "".join(source[p.start : p.end] for p in prepared.parts if p.kind == "protected")
    assert "`a()`" in protected
    assert "/url" not in prepared.text
    assert segment.text == source
    assert "".join(source[p.start : p.end] for p in prepared.parts) == source
