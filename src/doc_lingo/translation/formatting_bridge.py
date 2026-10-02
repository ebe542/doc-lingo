"""Connect original source scopes, model alignment and restored target text."""

from collections.abc import Callable
from dataclasses import dataclass, replace

from doc_lingo.translation.alignment import AlignmentError, AlignmentResult, TextRange
from doc_lingo.translation.formatting import (
    FormattingIssue,
    FormattingProjection,
    FormattingScope,
    ProjectedFormatting,
    project_formatting,
)
from doc_lingo.translation.issues import TranslationDiagnostics, TranslationIssue
from doc_lingo.translation.marker_alignment import anchor_content_markers
from doc_lingo.translation.model_input import ModelInput


@dataclass(frozen=True)
class RestoredFormatting:
    """Target ranges address text; scope references address original source."""

    text: str
    projection: FormattingProjection


def _source_position(prepared: ModelInput, position: int) -> int:
    markers = {(m.start, m.end): m.token for m in prepared.markers}
    offset = 0
    for part in prepared.source.parts:
        token = markers.get((part.start, part.end))
        size = 0 if part.kind == "syntax" else len(token) if token else part.end - part.start
        if position <= part.start:
            return offset
        if position < part.end:
            if token:
                raise AlignmentError("Formatting boundary splits protected content")
            return offset if part.kind == "syntax" else offset + position - part.start
        offset += size
    return offset


def restore_aligned_formatting(
    prepared: ModelInput,
    alignment: AlignmentResult,
    scopes: tuple[FormattingScope, ...],
    *,
    segment_id: str,
    segment_type: str,
    segment_number: int,
    paragraph_number: int | None = None,
    page: int | None = None,
    on_issue: Callable[[TranslationIssue], None] | None = None,
) -> RestoredFormatting:
    """Project scopes supplied in original-document-segment coordinates.

    Call after translation, before marker replacement, for one complete prepared
    segment. Invalid markers raise AlignmentError before restoring anything.
    A scope cutting opaque content is dropped rather than guessing an offset.
    Returned scopes retain their original coordinates and adapter identities.
    Diagnostics use the existing TranslationIssue callback/file-log contract;
    callback failures propagate. No global issue context is changed.
    """
    if prepared.text is None:
        raise AlignmentError("Fully protected input must bypass alignment")
    anchored = anchor_content_markers(alignment, prepared)
    original = prepared.source.layout.source
    by_id = {scope.identity: scope for scope in scopes}
    if len(by_id) != len(scopes):
        raise ValueError("Formatting identities must be unique")
    mapped = []
    issues = []
    for scope in scopes:
        if scope.source.end > len(original):
            raise ValueError("Formatting scope exceeds original source")
        try:
            start = _source_position(prepared, scope.source.start)
            end = _source_position(prepared, scope.source.end)
        except AlignmentError:
            issues.append(FormattingIssue(scope.identity, "dropped", "partial_protected_content"))
            continue
        if start == end:
            issues.append(FormattingIssue(scope.identity, "dropped", "no_visible_content"))
            continue
        mapped.append(replace(scope, source=TextRange(start, end)))
    projection = project_formatting(anchored, tuple(mapped))
    issues.extend(projection.issues)

    # Single-pass substitution avoids interpreting marker-like original content.
    replacements = sorted(
        (alignment.target.index(m.token), m.token, original[m.start : m.end])
        for m in prepared.markers
    )
    pieces = []
    cursor = 0
    for start, token, content in replacements:
        pieces.extend((alignment.target[cursor:start], content))
        cursor = start + len(token)
    pieces.append(alignment.target[cursor:])
    text = "".join(pieces)

    def target_position(position: int) -> int:
        shift = 0
        for start, token, content in replacements:
            end = start + len(token)
            if start < position < end:
                raise AlignmentError("Projected boundary splits a content marker")
            if end <= position:
                shift += len(content) - len(token)
        return position + shift

    restored = tuple(
        ProjectedFormatting(
            by_id[item.scope.identity],
            tuple(
                TextRange(target_position(r.start), target_position(r.end))
                for r in item.target_ranges
            ),
        )
        for item in projection.formatting
    )
    result = RestoredFormatting(text, FormattingProjection(restored, tuple(issues)))
    if on_issue is not None:
        for issue in issues:
            on_issue(
                TranslationIssue(
                    original,
                    "Formatting projection: " + issue.reason,
                    segment_id,
                    segment_type,
                    segment_number,
                    paragraph_number,
                    page=page,
                    action="formatting_" + issue.action,
                    diagnostics=TranslationDiagnostics(
                        text,
                        "formatting_projection",
                        (f"{issue.identity}: {issue.reason}",),
                    ),
                )
            )
    return result
