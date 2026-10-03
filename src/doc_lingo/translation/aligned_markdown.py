"""Opt-in complete-segment Markdown translation and alignment orchestration."""

from doc_lingo.documents.markdown._parser import _MarkdownSegment
from doc_lingo.documents.markdown.aligned import (
    AlignedMarkdownSegment,
    aligned_body,
    aligned_errors,
)
from doc_lingo.documents.markdown.rendering import markdown_scopes, render_markdown
from doc_lingo.translation.alignment import AlignmentError, AlignmentResult, TextRange
from doc_lingo.translation.formatting_bridge import restore_aligned_formatting
from doc_lingo.translation.issues import (
    RecoverableTranslationError,
    TranslationDiagnostics,
    issue_sink,
    retain_original,
)
from doc_lingo.translation.model_input import prepare_model_input


def translate_aligned(segment, backend, aligner, *, source_lang, target_lang, report):
    """Return evidence for the writer, or None for unsupported HTML segments."""
    if not isinstance(segment, _MarkdownSegment):
        return None
    layout = segment.source_layout()
    if any(layout.source[r.outer_start : r.inner_start].startswith("<") for r in layout.ranges):
        return None
    leading, body, trailing = aligned_body(segment)
    layout = body.source_layout()
    prepared = prepare_model_input(body.translation_input())
    if prepared.text is None:
        return AlignedMarkdownSegment(segment.id, segment.text, segment.type)
    failures = []
    token = issue_sink.set(lambda original, reason: failures.append(reason))
    try:
        try:
            target = backend.translate(
                prepared.text, source_lang=source_lang, target_lang=target_lang
            )
        except RecoverableTranslationError as exc:
            failures.append(str(exc))
            target = ""
    finally:
        issue_sink.reset(token)
    if failures:
        text = retain_original(
            segment.text,
            "Backend recovery during aligned translation",
            diagnostics=TranslationDiagnostics(target, "aligned_backend", tuple(failures)),
        )
        return AlignedMarkdownSegment(segment.id, text, segment.type)
    try:
        if not target.strip():
            raise AlignmentError("Empty aligned translation")
        try:
            alignment = aligner.align(prepared.text, target)
            if alignment.source != prepared.text or alignment.target != target:
                raise AlignmentError("Aligner returned mismatched text")
        except AlignmentError:
            # Encoder limits or unavailable correspondences must not discard a
            # valid translation. Marker validation still runs in the bridge.
            alignment = AlignmentResult(
                prepared.text, target, unaligned=(TextRange(0, len(prepared.text)),)
            )
            report(
                segment.text, "Alignment failed; formatting omitted", action="formatting_dropped"
            )
        restored = restore_aligned_formatting(
            prepared,
            alignment,
            markdown_scopes(layout),
            segment_id=segment.id,
            segment_type=segment.type,
            segment_number=0,
        )
    except AlignmentError as error:
        text = retain_original(
            segment.text,
            "Aligned content validation failed; source retained",
            diagnostics=TranslationDiagnostics(target, "aligned_content", (str(error),)),
        )
        return AlignedMarkdownSegment(segment.id, text, segment.type)
    rendered = render_markdown(layout, restored, environment=segment.environment)
    translated = AlignedMarkdownSegment(
        segment.id, leading + rendered.text + trailing, segment.type, restored=restored
    )
    errors = aligned_errors(segment, translated)
    if errors:
        text = retain_original(
            segment.text,
            "Aligned Markdown structure changed; source retained",
            diagnostics=TranslationDiagnostics(translated.text, "aligned_structure", errors),
        )
        return AlignedMarkdownSegment(segment.id, text, segment.type)
    for issue in rendered.issues:
        report(
            segment.text,
            "Formatting projection: " + issue.reason,
            action="formatting_" + issue.action,
            diagnostics=TranslationDiagnostics(
                rendered.text, "formatting_projection", (f"{issue.identity}: {issue.reason}",)
            ),
        )
    return translated
