"""Reconstruct TXT from reviewed text using the unchanged job snapshot."""

from pathlib import Path
from tempfile import TemporaryDirectory

from doc_lingo.documents.plain_text import PlainTextWriter
from doc_lingo.review.jobs import ReviewJob
from doc_lingo.review.text import import_review_txt


def finalize_text_review(
    job: ReviewJob,
    review: str | Path,
    destination: str | Path,
    *,
    original: str | Path | None = None,
) -> None:
    """Publish a new TXT; optionally verify an external original before import.

    No translation or alignment is performed. The stored source is authoritative;
    source filename metadata is never resolved as a filesystem path.
    """
    if original is not None:
        job.verify_source(original)
    segments = import_review_txt(job, review)
    destination = Path(destination)
    with TemporaryDirectory(
        prefix=".doc-lingo-review-source-", dir=destination.parent
    ) as directory:
        snapshot = Path(directory) / "source.txt"
        snapshot.write_bytes(job.source)
        PlainTextWriter(snapshot).write(destination, segments)
