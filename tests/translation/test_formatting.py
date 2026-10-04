"""Projection policy is independent of models and document syntax."""

from dataclasses import asdict

import pytest

from doc_lingo.translation.alignment import AlignmentLink, AlignmentResult, TextRange
from doc_lingo.translation.formatting import FormattingScope, project_formatting


def sample():
    return AlignmentResult(
        "turned off device",
        "schaltete Gerät aus",
        (
            AlignmentLink((TextRange(0, 6),), (TextRange(0, 9),)),
            AlignmentLink((TextRange(7, 10),), (TextRange(16, 19),)),
            AlignmentLink((TextRange(11, 17),), (TextRange(10, 15),)),
        ),
    )


def test_style_splits_and_link_expands_without_changing_destination():
    alignment = sample()
    style = FormattingScope("bold", TextRange(0, 10))
    link = FormattingScope("link", TextRange(0, 10), "https://example.org/a?q=1#part")
    result = project_formatting(alignment, (style, link))
    assert result.formatting[0].target_ranges == (TextRange(0, 9), TextRange(16, 19))
    assert result.formatting[1].target_ranges == (TextRange(0, 19),)
    assert result.formatting[1].scope.link_target == link.link_target
    assert [issue.action for issue in result.issues] == ["split", "expanded"]
    assert "https" not in str(asdict(result.issues[1]))
    assert alignment.target == "schaltete Gerät aus"


@pytest.mark.parametrize("reverse", [False, True])
def test_expanded_link_conflicts_drop_both_links_but_keep_style(reverse):
    scopes = (
        FormattingScope("outer", TextRange(0, 10), "a"),
        FormattingScope("inner", TextRange(11, 17), "b"),
        FormattingScope("style", TextRange(11, 17)),
    )
    result = project_formatting(sample(), scopes[::-1] if reverse else scopes)
    assert [item.scope.identity for item in result.formatting] == ["style"]
    assert {issue.identity for issue in result.issues} == {"outer", "inner"}
    assert all(issue.reason == "overlapping_links" for issue in result.issues)
    assert all(issue.action == "dropped" for issue in result.issues)


def test_disjoint_links_survive():
    result = project_formatting(
        sample(),
        (
            FormattingScope("a", TextRange(0, 6), "a"),
            FormattingScope("b", TextRange(7, 10), "b"),
        ),
    )
    assert len(result.formatting) == 2
    assert not result.issues


@pytest.mark.parametrize("status", ["unaligned", "ambiguous"])
def test_unresolved_scope_drops_only_formatting(status):
    alignment = AlignmentResult("word", "Wort", **{status: (TextRange(0, 4),)})
    result = project_formatting(alignment, (FormattingScope("x", TextRange(0, 4)),))
    assert not result.formatting
    assert result.issues[0].reason == "unresolved_source"
    assert alignment.target == "Wort"


def test_group_crossing_scope_boundary_is_not_guessed():
    alignment = AlignmentResult(
        "a b", "ab", (AlignmentLink((TextRange(0, 1), TextRange(2, 3)), (TextRange(0, 2),)),)
    )
    result = project_formatting(alignment, (FormattingScope("x", TextRange(0, 1)),))
    assert not result.formatting
    assert result.issues[0].reason == "crossing_source_boundary"


def test_multi_sentence_scope_merges_whitespace_gaps():
    alignment = AlignmentResult(
        "One. Two.",
        "Eins. Zwei.",
        (
            AlignmentLink((TextRange(0, 4),), (TextRange(0, 5),)),
            AlignmentLink((TextRange(5, 9),), (TextRange(6, 11),)),
        ),
    )
    result = project_formatting(alignment, (FormattingScope("x", TextRange(0, 9)),))
    assert result.formatting[0].target_ranges == (TextRange(0, 11),)
    assert not result.issues


def test_inserted_words_split_style_even_without_other_source_links():
    alignment = AlignmentResult(
        "a b",
        "A extra B",
        (
            AlignmentLink((TextRange(0, 1),), (TextRange(0, 1),)),
            AlignmentLink((TextRange(2, 3),), (TextRange(8, 9),)),
        ),
    )
    result = project_formatting(alignment, (FormattingScope("x", TextRange(0, 3)),))
    assert result.formatting[0].target_ranges == (TextRange(0, 1), TextRange(8, 9))
    assert result.issues[0].action == "split"


def test_empty_and_whitespace_scopes():
    alignment = AlignmentResult(" ", " ")
    assert not project_formatting(alignment, ()).issues
    result = project_formatting(alignment, (FormattingScope("x", TextRange(0, 1)),))
    assert not result.formatting
    assert result.issues[0].reason == "no_target"


def test_invalid_coordinates_and_duplicate_identity():
    with pytest.raises(ValueError, match="exceeds"):
        project_formatting(sample(), (FormattingScope("x", TextRange(0, 99)),))
    scope = FormattingScope("x", TextRange(0, 6))
    with pytest.raises(ValueError, match="unique"):
        project_formatting(sample(), (scope, scope))


@pytest.mark.parametrize("destination", [None, "https://example.org"])
@pytest.mark.parametrize("status", ["unaligned", "ambiguous"])
def test_complete_segment_scope_does_not_need_word_links(destination, status):
    alignment = AlignmentResult(" word ", " Ein Wort ", **{status: (TextRange(1, 5),)})
    scope = FormattingScope("x", TextRange(1, 5), destination)
    result = project_formatting(alignment, (scope,), complete_segment=True)
    assert result.formatting[0].target_ranges == (TextRange(1, 9),)
    assert not result.issues


def test_partial_scope_remains_strict_and_reports_coordinates():
    alignment = AlignmentResult("word other", "Wort anderes", unaligned=(TextRange(0, 10),))
    scope = FormattingScope("x", TextRange(0, 4))
    result = project_formatting(alignment, (scope,), complete_segment=True)
    assert not result.formatting
    assert result.issues[0].source_ranges == (TextRange(0, 4),)
    assert "alignment_source_ranges=[0,4)" in result.issues[0].diagnostic()


def test_complete_segment_does_not_format_empty_target():
    alignment = AlignmentResult("word", " ", unaligned=(TextRange(0, 4),))
    assert not project_formatting(
        alignment, (FormattingScope("x", TextRange(0, 4)),), complete_segment=True
    ).formatting


def test_complete_link_still_conflicts_with_nested_link():
    scopes = (
        FormattingScope("outer", TextRange(0, 17), "a"),
        FormattingScope("inner", TextRange(11, 17), "b"),
    )
    result = project_formatting(sample(), scopes, complete_segment=True)
    assert not result.formatting
    assert all(issue.reason == "overlapping_links" for issue in result.issues)
