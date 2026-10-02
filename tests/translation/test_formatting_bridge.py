"""Exercise coordinate conversion with moved markers and real source layouts."""

from dataclasses import replace

import pytest

from doc_lingo.documents.source_layout import SourceLayout, SourceRange
from doc_lingo.documents.translation_input import TranslationInput
from doc_lingo.translation.alignment import (
    AlignmentError,
    AlignmentLink,
    AlignmentResult,
    TextRange,
)
from doc_lingo.translation.formatting import FormattingScope
from doc_lingo.translation.formatting_bridge import restore_aligned_formatting
from doc_lingo.translation.model_input import prepare_model_input


def example():
    layout = SourceLayout("**ab** xx cd", (SourceRange(0, 2, 4, 6),))
    prepared = prepare_model_input(TranslationInput.from_layout(layout, ((7, 9),)))
    marker = prepared.markers[0].token
    n = len(marker)
    target = f"CD {marker} AB"
    alignment = AlignmentResult(
        prepared.text,
        target,
        (
            AlignmentLink((TextRange(0, 2),), (TextRange(n + 4, n + 6),)),
            AlignmentLink((TextRange(3, 3 + n),), (TextRange(3, 3 + n),)),
            AlignmentLink((TextRange(n + 4, n + 6),), (TextRange(0, 2),)),
        ),
    )
    return prepared, alignment


def run(prepared, alignment, scopes=(), **kwargs):
    return restore_aligned_formatting(
        prepared,
        alignment,
        scopes,
        segment_id="p1",
        segment_type="paragraph",
        segment_number=2,
        paragraph_number=1,
        page=3,
        **kwargs,
    )


def test_original_wrappers_and_marker_lengths_map_to_restored_target():
    prepared, alignment = example()
    scopes = (FormattingScope("bold", TextRange(0, 6)), FormattingScope("code", TextRange(7, 9)))
    result = run(prepared, alignment, scopes)
    assert result.text == "CD xx AB"
    assert result.projection.formatting[0].target_ranges == (TextRange(6, 8),)
    assert result.projection.formatting[1].target_ranges == (TextRange(3, 5),)
    assert tuple(item.scope for item in result.projection.formatting) == scopes
    assert not result.projection.issues


def test_contiguous_target_does_not_emit_unnecessary_issue():
    prepared, alignment = example()
    reports = []
    result = run(
        prepared,
        alignment,
        (FormattingScope("link", TextRange(0, 9), "https://example.org"),),
        on_issue=reports.append,
    )
    # AB and the adjacent marker join across whitespace, so no expansion needed.
    assert result.projection.formatting[0].target_ranges == (TextRange(3, 8),)
    assert reports == []


@pytest.mark.parametrize("destination,action", [(None, "split"), ("url", "expanded")])
def test_projection_issues_forwarded_without_markers(destination, action):
    prepared = prepare_model_input(TranslationInput.from_layout(SourceLayout("ab cd ef")))
    alignment = AlignmentResult(
        "ab cd ef",
        "AB EF CD",
        (
            AlignmentLink((TextRange(0, 2),), (TextRange(0, 2),)),
            AlignmentLink((TextRange(3, 5),), (TextRange(6, 8),)),
            AlignmentLink((TextRange(6, 8),), (TextRange(3, 5),)),
        ),
    )
    reports = []
    result = run(
        prepared,
        alignment,
        (FormattingScope("x", TextRange(0, 5), destination),),
        on_issue=reports.append,
    )
    assert result.text == "AB EF CD"
    assert reports[0].action == "formatting_" + action
    assert result.projection.issues[0].action == action


def test_missing_marker_raises_before_any_callback():
    prepared, _ = example()
    alignment = AlignmentResult(prepared.text, "missing", (), (TextRange(0, len(prepared.text)),))
    reports = []
    with pytest.raises(AlignmentError):
        run(prepared, alignment, on_issue=reports.append)
    assert not reports


@pytest.mark.parametrize(
    "span,reason",
    [
        (TextRange(7, 8), "partial_protected_content"),
        (TextRange(0, 1), "no_visible_content"),
    ],
)
def test_unmappable_scope_is_dropped_and_logged_with_context(span, reason):
    prepared, alignment = example()
    reports = []
    result = run(prepared, alignment, (FormattingScope("x", span),), on_issue=reports.append)
    assert result.text == "CD xx AB"
    assert not result.projection.formatting
    assert result.projection.issues[0].reason == reason
    issue = reports[0]
    assert issue.action == "formatting_dropped"
    assert (issue.segment_id, issue.segment_number, issue.paragraph_number, issue.page) == (
        "p1",
        2,
        1,
        3,
    )
    assert issue.diagnostics.stage == "formatting_projection"
    assert issue.diagnostics.attempted_translation == result.text


def test_invalid_input_is_rejected_before_reporting():
    prepared, alignment = example()
    with pytest.raises(AlignmentError):
        run(replace(prepared, text=None), alignment)
    with pytest.raises(AlignmentError):
        run(replace(prepared, text="wrong"), alignment)
    scope = FormattingScope("x", TextRange(0, 2))
    with pytest.raises(ValueError, match="unique"):
        run(prepared, alignment, (scope, scope))
    with pytest.raises(ValueError, match="exceeds"):
        run(prepared, alignment, (FormattingScope("x", TextRange(0, 100)),))


def test_callback_failure_propagates():
    prepared, alignment = example()

    def fail(issue):
        raise RuntimeError("log unavailable")

    with pytest.raises(RuntimeError, match="log unavailable"):
        run(prepared, alignment, (FormattingScope("x", TextRange(0, 1)),), on_issue=fail)
