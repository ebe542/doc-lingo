"""Read source-preserving Markdown segments."""

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path

from doc_lingo.documents.markdown._parser import _regions
from doc_lingo.documents.models import TextSegment


class MarkdownReader:
    """Extract ordered Markdown text; preserve unsupported constructs verbatim."""

    def __init__(self, source: str | Path) -> None:
        self.source = Path(source)

    @contextmanager
    def iter_segments(self) -> Generator[Iterator[TextSegment], None, None]:
        with self.source.open(encoding="utf-8-sig", newline="") as stream:
            segments = (region.segment for region in _regions(stream.read()))
            try:
                yield segments
            finally:
                segments.close()
