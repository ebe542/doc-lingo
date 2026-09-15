"""Format-independent document translation orchestration."""

from contextlib import closing
from pathlib import Path

from doc_lingo.documents import DocumentReader, DocumentWriter, TextSegment
from doc_lingo.translation.protocols import TranslationBackend


def translate_document(
    reader: DocumentReader,
    writer: DocumentWriter,
    backend: TranslationBackend,
    destination: Path,
    *,
    source_lang: str,
    target_lang: str,
) -> None:
    """Translate ordered segments while keeping the reading session open.

    Reader and writer must refer to the same unchanged source document. The
    backend is caller-owned. Errors propagate without logging or wrapping; the
    writer owns output cleanup and publication. No retries or model chunking
    are performed here.
    """
    with reader.iter_segments() as segments:
        translations = (
            TextSegment(
                id=segment.id,
                text=backend.translate(
                    segment.text, source_lang=source_lang, target_lang=target_lang
                ),
            )
            for segment in segments
        )
        # The writer consumes lazily. Close our generator before the reader's
        # context exits, including when writing fails or stops consuming early.
        with closing(translations):
            writer.write(destination, translations)
