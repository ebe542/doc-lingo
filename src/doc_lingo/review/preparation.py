"""Create proposal jobs through the existing translation and recovery service."""

from collections.abc import Callable, Iterable
from pathlib import Path
from tempfile import TemporaryDirectory

from doc_lingo.documents.models import TextSegment
from doc_lingo.documents.plain_text import PlainTextReader
from doc_lingo.review.jobs import ReviewJob, create_text_job
from doc_lingo.translation.issues import TranslationIssue
from doc_lingo.translation.protocols import TranslationBackend
from doc_lingo.translation.service import translate_document


class _JobWriter:
    def __init__(self, snapshot: Path, source_lang: str, target_lang: str):
        self.snapshot = snapshot
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.job: ReviewJob | None = None

    def write(self, destination: Path, translations: Iterable[TextSegment]) -> None:
        self.job = create_text_job(
            self.snapshot, translations, source_lang=self.source_lang, target_lang=self.target_lang
        )


def translate_text_job(
    source: str | Path,
    backend: TranslationBackend,
    *,
    source_lang: str,
    target_lang: str,
    on_progress: Callable[[int, str], None] | None = None,
    on_issue: Callable[[TranslationIssue], None] | None = None,
) -> ReviewJob:
    """Translate an immutable TXT snapshot; verify the external source afterward.

    With on_issue, the translation service retains recoverable failures as source
    text. Without it, recovery stays strict. Temporary snapshots are always removed.
    """
    source = Path(source)
    data = source.read_bytes()
    with TemporaryDirectory(prefix="doc-lingo-review-source-") as directory:
        snapshot = Path(directory) / source.name
        snapshot.write_bytes(data)
        writer = _JobWriter(snapshot, source_lang, target_lang)
        translate_document(
            PlainTextReader(snapshot),
            writer,
            backend,
            snapshot,
            source_lang=source_lang,
            target_lang=target_lang,
            on_progress=on_progress,
            on_issue=on_issue,
        )
        assert writer.job is not None
        writer.job.verify_source(source)
        return writer.job
