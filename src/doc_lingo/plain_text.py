"""Incremental UTF-8 paragraph reading."""

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO

from doc_lingo.documents import TextSegment


class PlainTextReader:
    """Read paragraphs separated by empty or whitespace-only lines.

    Separator lines are omitted. Line endings inside paragraph text are retained,
    including the final line ending. An optional UTF-8 BOM is not translatable
    text and is removed on input. This is extraction, not lossless reconstruction.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @contextmanager
    def iter_segments(self) -> Generator[Iterator[TextSegment], None, None]:
        """Open an independent session and close it on every context exit.

        File-system and UTF-8 decoding errors propagate to the caller. Memory
        use scales with the largest paragraph: a file without blank lines is
        one paragraph. Extensions are not validated.
        """
        # Recognize platform line endings without converting them.
        with self.path.open("r", encoding="utf-8-sig", newline="") as source:
            segments = self._read_paragraphs(source)
            try:
                yield segments
            finally:
                # Discard buffered state when a consumer stops early as well.
                segments.close()

    @staticmethod
    def _read_paragraphs(source: TextIO) -> Generator[TextSegment, None, None]:
        lines: list[str] = []
        number = 0
        for line in source:
            if line.strip():
                lines.append(line)
            elif lines:
                number += 1
                segment = TextSegment(id=str(number), text="".join(lines))
                lines.clear()
                yield segment
        if lines:
            yield TextSegment(id=str(number + 1), text="".join(lines))
