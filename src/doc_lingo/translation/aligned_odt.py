"""Opt-in ODT projection through the shared paired translation/alignment path."""

from doc_lingo.documents.odt.aligned import (
    AlignedOdtSegment,
    odt_scopes,
    render_aligned,
    supports_projection,
)
from doc_lingo.documents.odt.inline import OdtInlineSegment
from doc_lingo.documents.odt.package import OdtPackageError
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


def translate_aligned_odt(
    segment, backend, aligner, *, source_lang, target_lang, report, statistics=None
):
    """Return None for the existing protected path when projection is unsupported."""
    if not isinstance(segment, OdtInlineSegment) or not supports_projection(segment):
        return None
    prepared = prepare_model_input(segment.translation_input())
    if prepared.text is None:
        return AlignedOdtSegment(segment.id, segment.text, segment.type)
    failures = []
    target = ""
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
                    "Chunk alignment failed; word correspondence unavailable",
                    action="formatting_dropped",
                    diagnostics=TranslationDiagnostics(None, "chunk_alignment", details),
                ),
            )
            target = alignment.target
        except (RecoverableTranslationError, AlignmentError) as error:
            failures.append(str(error))
    finally:
        issue_sink.reset(token)
    if failures:
        text = retain_original(
            segment.text,
            "Backend recovery during aligned ODT translation",
            diagnostics=TranslationDiagnostics(target, "aligned_backend", tuple(failures)),
        )
        return AlignedOdtSegment(segment.id, text, segment.type)
    try:
        if not target.strip():
            raise AlignmentError("Empty aligned translation")
        restored = restore_aligned_formatting(
            prepared,
            alignment,
            odt_scopes(segment),
            segment_id=segment.id,
            segment_type=segment.type,
            segment_number=0,
        )
        rendered, issues = render_aligned(segment, restored)
    except (AlignmentError, OdtPackageError) as error:
        text = retain_original(
            segment.text,
            "Aligned ODT content validation failed; source retained",
            diagnostics=TranslationDiagnostics(target, "aligned_content", (str(error),)),
        )
        return AlignedOdtSegment(segment.id, text, segment.type)
    for issue in issues:
        report(
            segment.text,
            "Formatting projection: " + issue.reason,
            action="formatting_" + issue.action,
            diagnostics=TranslationDiagnostics(
                rendered, "formatting_projection", (issue.diagnostic(),)
            ),
        )
    return AlignedOdtSegment(segment.id, rendered, segment.type, restored=restored)
