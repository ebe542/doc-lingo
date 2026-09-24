"""Format-independent document translation orchestration."""

from collections.abc import Callable, Generator
from contextlib import closing
from pathlib import Path

from doc_lingo.documents import DocumentReader, DocumentWriter, TextSegment
from doc_lingo.translation.issues import TranslationIssue, issue_sink, retain_original
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
    """
    with reader.iter_segments() as segments:

        def translated_segments() -> Generator[TextSegment, None, None]:
            paragraph = 0
            for count, segment in enumerate(segments, start=1):
                if segment.type == "paragraph":
                    paragraph += 1

                def report(
                    original: str, reason: str, segment=segment, count=count, paragraph=paragraph
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
                            )
                        )

                token = issue_sink.set(report if on_issue is not None else None)
                try:
                    text = translate_segment(
                        segment, backend, source_lang=source_lang, target_lang=target_lang
                    )
                    if not segment.accepts_translation(text):
                        text = retain_original(
                            segment.text, "Document structure changed; source retained"
                        )
                finally:
                    issue_sink.reset(token)
                translated = TextSegment(
                    id=segment.id,
                    text=text,
                    type=segment.type,
                )
                if on_progress is not None:
                    on_progress(count, segment.type)
                yield translated

        translations = translated_segments()
        # The writer consumes lazily. Close our generator before the reader's
        # context exits, including when writing fails or stops consuming early.
        with closing(translations):
            writer.write(destination, translations)
