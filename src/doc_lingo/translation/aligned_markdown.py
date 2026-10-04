"""Opt-in complete-segment Markdown translation and alignment orchestration."""

from doc_lingo.documents.html.text import HtmlSegment
from doc_lingo.documents.markdown._parser import _MarkdownSegment
from doc_lingo.documents.markdown.aligned import (
    AlignedMarkdownSegment,
    aligned_body,
    aligned_errors,
)
from doc_lingo.documents.markdown.rendering import html_wrapper, markdown_scopes, render_markdown
from doc_lingo.translation.aligned_chunks import translate_aligned_chunks
from doc_lingo.translation.alignment import AlignmentError
from doc_lingo.translation.formatting_bridge import restore_aligned_formatting
from doc_lingo.translation.issues import (
    RecoverableTranslationError,
    TranslationDiagnostics,
    issue_sink,
    retain_original,
)
from doc_lingo.translation.model_input import prepare_model_input


def translate_aligned(
    segment, backend, aligner, *, source_lang, target_lang, report, statistics=None
):
    """Return evidence for the writer, or None for unsupported HTML segments."""
    if not isinstance(segment, (_MarkdownSegment, HtmlSegment)):
        return None
    layout = segment.source_layout()
    if any(
        layout.source[r.outer_start : r.inner_start].startswith("<")
        and html_wrapper(
            layout.source[r.outer_start : r.inner_start], layout.source[r.inner_end : r.outer_end]
        )
        is None
        for r in layout.ranges
    ):
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
            alignment = translate_aligned_chunks(
                prepared.text,
                backend,
                aligner,
                source_lang=source_lang,
                target_lang=target_lang,
                protected_tokens=tuple(marker.token for marker in prepared.markers),
                statistics=statistics,
                on_alignment_failure=lambda details: report(
                    segment.text,
                    "Chunk alignment failed; affected formatting omitted",
                    action="formatting_dropped",
                    diagnostics=TranslationDiagnostics(None, "chunk_alignment", details),
                ),
            )
            target = alignment.target
        except (RecoverableTranslationError, AlignmentError) as exc:
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
    rendered = render_markdown(
        layout,
        restored,
        environment=segment.environment if isinstance(segment, _MarkdownSegment) else {},
        raw_html=isinstance(segment, HtmlSegment),
    )
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
                rendered.text, "formatting_projection", (issue.diagnostic(),)
            ),
        )
    return translated
