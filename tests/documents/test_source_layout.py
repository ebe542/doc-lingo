"""Source-only extraction preserves content and rejects ambiguous layouts."""

import pytest

from doc_lingo.documents import SourceLayout, SourceRange


@pytest.mark.parametrize("source", ["", "plain text", "  ä😀\t\r\nnext\n", r"a\* &amp;"])
def test_unformatted_source_is_unchanged(source):
    assert SourceLayout(source).extract_text() == source


def test_emphasis_retains_original_slices():
    source = "The **model** works."
    span = SourceRange(4, 6, 11, 13)
    layout = SourceLayout(source, (span,))
    assert layout.extract_text() == "The model works."
    assert layout.source == source
    assert source[span.outer_start : span.inner_start] == "**"
    assert source[span.inner_start : span.inner_end] == "model"
    assert source[span.inner_end : span.outer_end] == "**"


def test_link_with_nested_emphasis_keeps_label_only():
    source = '[the **model**](https://example.org "Title")'
    layout = SourceLayout(
        source,
        (SourceRange(0, 1, 14, len(source)), SourceRange(5, 7, 12, 14)),
    )
    assert layout.extract_text() == "the model"


def test_nested_siblings_and_following_range():
    source = "<b><i>a</i><i>b</i></b><i>c</i>"
    layout = SourceLayout(
        source,
        (
            SourceRange(0, 3, 19, 23),
            SourceRange(3, 6, 7, 11),
            SourceRange(11, 14, 15, 19),
            SourceRange(23, 26, 27, 31),
        ),
    )
    assert layout.extract_text() == "abc"


def test_repeated_words_are_identified_by_position():
    source = "model **model** model"
    assert SourceLayout(source, (SourceRange(6, 8, 13, 15),)).extract_text() == (
        "model model model"
    )


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_unicode_offsets_and_line_endings(newline):
    source = "😀 **ä**" + newline + "終"
    assert SourceLayout(source, (SourceRange(2, 4, 5, 7),)).extract_text() == (
        "😀 ä" + newline + "終"
    )


@pytest.mark.parametrize(
    "source,span,expected",
    [
        ("<b></b>", SourceRange(0, 3, 3, 7), ""),
        ("word", SourceRange(0, 0, 4, 4), "word"),
        ("*word", SourceRange(0, 1, 5, 5), "word"),
        ("word*", SourceRange(0, 0, 4, 5), "word"),
        ("**&amp;**", SourceRange(0, 2, 7, 9), "&amp;"),
        (r"**a\*b**", SourceRange(0, 2, 6, 8), r"a\*b"),
    ],
)
def test_empty_content_and_literal_extraction(source, span, expected):
    assert SourceLayout(source, (span,)).extract_text() == expected


@pytest.mark.parametrize(
    "offsets",
    [(-1, 0, 1, 2), (2, 1, 3, 4), (0, 3, 2, 4), (0, 1, 4, 3), (1, 1, 1, 1)],
)
def test_invalid_boundaries(offsets):
    with pytest.raises(ValueError):
        SourceRange(*offsets)


@pytest.mark.parametrize(
    "ranges",
    [
        (SourceRange(0, 1, 9, 11),),  # Beyond the source.
        (SourceRange(0, 1, 2, 3), SourceRange(0, 1, 2, 3)),  # Duplicate.
        (SourceRange(5, 6, 7, 8), SourceRange(0, 1, 2, 3)),  # Reversed order.
        (SourceRange(0, 1, 5, 6), SourceRange(4, 5, 7, 8)),  # Crossing.
        (SourceRange(0, 3, 7, 10), SourceRange(1, 1, 2, 2)),  # Opening syntax.
        (SourceRange(0, 3, 7, 10), SourceRange(8, 8, 9, 9)),  # Closing syntax.
        (SourceRange(2, 3, 4, 5), SourceRange(2, 2, 6, 7)),  # Child before parent.
    ],
)
def test_invalid_layouts(ranges):
    with pytest.raises(ValueError):
        SourceLayout("0123456789", ranges)
