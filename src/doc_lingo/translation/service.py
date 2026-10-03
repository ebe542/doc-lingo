"""Format-independent document translation orchestration."""

from collections.abc import Callable, Generator
from contextlib import closing
from pathlib import Path

from doc_lingo.documents import DocumentReader, DocumentWriter, TextSegment
from doc_lingo.translation.alignment import TextAligner
from doc_lingo.translation.issues import (
    TranslationDiagnostics,
    TranslationIssue,
    issue_details,
    issue_sink,
    retain_original,
)
from doc_lingo.translation.protected import translate_segment
from doc_lingo.translation.protocols import TranslationBackend


def translate_document(
    reader: DocumentReader,
    writer: DocumentWriter,
    backend: TranslationBackend,
    destination: Path,
    *,
    source_lang: str,
    target_lang: str,
    on_progress: Callable[[int, str], None] | None = None,
    on_issue: Callable[[TranslationIssue], None] | None = None,
    aligner: TextAligner | None = None,
) -> None:
    """Translate ordered segments while keeping the reading session open.

    Reader and writer must refer to the same unchanged source document. The
    backend is caller-owned. Errors propagate without logging or wrapping; the
    writer owns output cleanup and publication. No retries or model chunking
    are performed here. The optional callback receives the completed translation
    count and segment type before handing the segment to the writer. This does
    not indicate publication. Translated segments retain their original type.
    Callback exceptions propagate and trigger normal resource cleanup.

    Supplying on_issue enables source retention for recoverable local-backend
    failures. Without it, library calls remain strict. The scoped context carries
    diagnostics without adding document-specific parameters to TranslationBackend;
    it is reset before yielding, including on exceptions and nested calls.

    An optional caller-owned aligner enables projected Markdown formatting.
    Other formats and unsupported HTML wrappers keep their existing path.
    Formatting warnings reach on_issue without counting as source retention.
    """
    with reader.iter_segments() as segments:

        def translated_segments() -> Generator[TextSegment, None, None]:
            paragraph = 0
            for count, segment in enumerate(segments, start=1):
                if segment.type == "paragraph":
                    paragraph += 1

                def report(
                    original: str,
                    reason: str,
                    segment=segment,
                    count=count,
                    paragraph=paragraph,
                    *,
                    action: str = "retained_original",
                    diagnostics: TranslationDiagnostics | None = None,
                ) -> None:
                    if on_issue is not None:
                        on_issue(
                            TranslationIssue(
                                original,
                                reason,
                                segment.id,
                                segment.type,
                                count,
                                paragraph if segment.type == "paragraph" else None,
                                action=action,
                                diagnostics=diagnostics or issue_details.get(),
                            )
                        )

                token = issue_sink.set(report if on_issue is not None else None)
                unrepaired_text = None
                aligned = None
                try:
                    if aligner is not None:
                        from doc_lingo.translation.aligned_markdown import translate_aligned

                        aligned = translate_aligned(
                            segment,
                            backend,
                            aligner,
                            source_lang=source_lang,
                            target_lang=target_lang,
                            report=report,
                        )
                    text = (
                        aligned.text
                        if aligned is not None
                        else translate_segment(
                            segment, backend, source_lang=source_lang, target_lang=target_lang
                        )
                    )
                    if aligned is None and not segment.accepts_translation(text):
                        diagnostics = TranslationDiagnostics(
                            text, "restored", segment.validation_errors(text)
                        )
                        repair = segment.repair_translation(text) if on_issue is not None else None
                        if repair is not None:
                            unrepaired_text, text = text, repair
                            report(
                                segment.text,
                                "Translation retained; newly empty emphasis removed",
                                action="formatting_repaired",
                                diagnostics=diagnostics,
                            )
                        else:
                            text = retain_original(
                                segment.text,
                                "Document structure changed; source retained",
                                diagnostics=diagnostics,
                            )
                finally:
                    issue_sink.reset(token)
                translated = (
                    aligned
                    if aligned is not None
                    else TextSegment(
                        id=segment.id,
                        text=text,
                        type=segment.type,
                        unrepaired_text=unrepaired_text,
                    )
                )
                if on_progress is not None:
                    on_progress(count, segment.type)
                yield translated

        translations = translated_segments()
        # The writer consumes lazily. Close our generator before the reader's
        # context exits, including when writing fails or stops consuming early.
        with closing(translations):
            writer.write(destination, translations)
