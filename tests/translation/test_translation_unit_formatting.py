"""Structural call evidence without manufacturing word correspondences."""

import pytest

from doc_lingo.translation.alignment import (
    AlignmentLink,
    AlignmentResult,
    TextRange,
    TranslationUnit,
)
from doc_lingo.translation.formatting import FormattingScope, project_formatting
from doc_lingo.translation.marker_alignment import anchor_registered_markers


def evidence():
    return AlignmentResult(
        "Intro. One two. End.",
        "Start. Eins zwei. Ende.",
        unaligned=(TextRange(0, 20),),
        units=(
            TranslationUnit(TextRange(0, 6), TextRange(0, 6)),
            TranslationUnit(TextRange(7, 15), TextRange(7, 17)),
            TranslationUnit(TextRange(16, 20), TextRange(18, 23)),
        ),
    )


@pytest.mark.parametrize("destination", [None, "https://example.org"])
def test_complete_unit_uses_structural_evidence(destination):
    result = evidence()
    scope = FormattingScope("a", TextRange(7, 15), destination)
    projected = project_formatting(result, (scope,))
    assert projected.formatting[0].target_ranges == (TextRange(7, 17),)
    assert not projected.issues
    assert not result.links
    assert result.unaligned == (TextRange(0, 20),)


def test_partial_boundary_stays_unresolved():
    result = project_formatting(evidence(), (FormattingScope("a", TextRange(7, 19)),))
    assert not result.formatting
    assert result.issues[0].source_ranges == (TextRange(16, 19),)


def test_multiple_complete_units_keep_separators():
    result = project_formatting(evidence(), (FormattingScope("a", TextRange(7, 20)),))
    assert result.formatting[0].target_ranges == (TextRange(7, 23),)
    assert not result.issues


@pytest.mark.parametrize("separator", [" ", "\t", "\n", "\r\n  ", " , "])
@pytest.mark.parametrize("status", ["unaligned", "ambiguous"])
def test_remaining_separators_need_no_word_link_but_punctuation_does(separator, status):
    source = "One." + separator + "Two."
    target = "Eins." + separator + "Zwei."
    alignment = AlignmentResult(
        source,
        target,
        **{status: (TextRange(0, len(source)),)},
        units=(
            TranslationUnit(TextRange(0, 4), TextRange(0, 5)),
            TranslationUnit(
                TextRange(4 + len(separator), len(source)),
                TextRange(5 + len(separator), len(target)),
            ),
        ),
    )
    result = project_formatting(alignment, (FormattingScope("a", TextRange(0, len(source))),))
    if separator.strip():
        assert not result.formatting
        assert result.issues[0].source_ranges == (TextRange(5, 6),)
    else:
        assert result.formatting[0].target_ranges == (TextRange(0, len(target)),)
        assert not result.issues
    assert getattr(alignment, status) == (TextRange(0, len(source)),)


def test_nested_styles_and_overlapping_links_keep_existing_policy():
    outer = FormattingScope("outer", TextRange(7, 20))
    inner = FormattingScope("inner", TextRange(7, 15))
    result = project_formatting(evidence(), (outer, inner))
    assert [item.target_ranges for item in result.formatting] == [
        (TextRange(7, 23),),
        (TextRange(7, 17),),
    ]
    links = (
        FormattingScope("outer", outer.source, "a"),
        FormattingScope("inner", inner.source, "b"),
    )
    result = project_formatting(evidence(), links)
    assert not result.formatting
    assert [issue.reason for issue in result.issues] == ["overlapping_links"] * 2


def test_partial_boundary_can_use_word_links():
    result = AlignmentResult(
        "One. two three",
        "Eins. zwei drei",
        (AlignmentLink((TextRange(5, 8),), (TextRange(6, 10),)),),
        (TextRange(0, 4), TextRange(9, 14)),
        units=(TranslationUnit(TextRange(0, 4), TextRange(0, 5)),),
    )
    projected = project_formatting(result, (FormattingScope("a", TextRange(0, 8)),))
    assert projected.formatting[0].target_ranges == (TextRange(0, 10),)
    assert not projected.issues


def test_cross_unit_marker_anchor_prevents_structural_override():
    raw = AlignmentResult(
        "DLMX0Z. word",
        "Wort. DLMX0Z",
        unaligned=(TextRange(0, 12),),
        units=(
            TranslationUnit(TextRange(0, 7), TextRange(0, 5)),
            TranslationUnit(TextRange(8, 12), TextRange(6, 12)),
        ),
    )
    anchored = anchor_registered_markers(raw, tokens=("DLMX0Z",), prefix="DLM")
    assert anchored.units == raw.units
    result = project_formatting(anchored, (FormattingScope("a", TextRange(0, 7)),))
    assert not result.formatting
    assert result.issues[0].reason == "unresolved_source"


@pytest.mark.parametrize(
    "units",
    [
        (TranslationUnit(TextRange(0, 5), TextRange(0, 1)),),
        (TranslationUnit(TextRange(0, 1), TextRange(0, 5)),),
        (
            TranslationUnit(TextRange(0, 2), TextRange(0, 2)),
            TranslationUnit(TextRange(1, 3), TextRange(2, 3)),
        ),
        (
            TranslationUnit(TextRange(0, 1), TextRange(2, 3)),
            TranslationUnit(TextRange(2, 3), TextRange(0, 1)),
        ),
    ],
)
def test_invalid_unit_coordinates_rejected(units):
    with pytest.raises(ValueError):
        AlignmentResult("abc", "ABC", unaligned=(TextRange(0, 3),), units=units)
