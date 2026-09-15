"""Format-independent document translation orchestration."""

from collections.abc import Callable, Generator
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
    on_progress: Callable[[int, str], None] | None = None,
) -> None:
    """Translate ordered segments while keeping the reading session open.

    Reader and writer must refer to the same unchanged source document. The
    backend is caller-owned. Errors propagate without logging or wrapping; the
    writer owns output cleanup and publication. No retries or model chunking
    are performed here. The optional callback receives the completed translation
    count and segment type before handing the segment to the writer. This does
    not indicate publication. Translated segments retain their original type.
    Callback exceptions propagate and trigger normal resource cleanup.
    """
    with reader.iter_segments() as segments:

        def translated_segments() -> Generator[TextSegment, None, None]:
            for count, segment in enumerate(segments, start=1):
                translated = TextSegment(
                    id=segment.id,
                    text=backend.translate(
                        segment.text, source_lang=source_lang, target_lang=target_lang
                    ),
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
