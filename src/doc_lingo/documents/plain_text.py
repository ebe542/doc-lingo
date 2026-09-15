"""Incremental UTF-8 paragraph reading."""

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO

from doc_lingo.documents.models import TextSegment
from doc_lingo.documents.text_blocks import iter_text_blocks


class PlainTextReader:
    """Read prose paragraphs and individual simple list items.

    Separator lines are omitted. Line endings inside paragraph text are retained,
    including the final line ending. An optional UTF-8 BOM is not translatable
    text and is removed on input. List markers and their indentation are omitted
    from translatable text and reconstructed by the writer from the original.
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
        number = 0
        for block in iter_text_blocks(source):
            if block.text is not None:
                number += 1
                yield TextSegment(id=str(number), text=block.text, type=block.type)
