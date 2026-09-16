"""Reconstruct UTF-8 documents from ordered translated paragraphs."""

import os
import re
import textwrap
from collections.abc import Iterable, Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TextIO

from doc_lingo.documents.errors import SegmentMismatchError
from doc_lingo.documents.models import TextSegment
from doc_lingo.documents.text_blocks import iter_text_blocks


class PlainTextWriter:
    """Retain the original BOM, separator lines, and paragraph-ending newlines.

    The source must remain unchanged since extraction. Internal line breaks come
    from the translation, with collapsed multiline prose reflowed; trailing CR/LF
    characters are replaced with the original
    paragraph ending. The caller owns and closes any translation generator.
    """

    def __init__(self, source: str | Path) -> None:
        self.source = Path(source)

    def write(self, destination: Path, translations: Iterable[TextSegment]) -> None:
        """Publish a complete new file without replacing an existing path.

        The destination directory must exist and support hard links. Unsupported
        file systems raise OSError instead of falling back to unsafe replacement.
        Temporary storage is cleaned up on success and on exceptions.
        """
        destination = Path(destination)
        if os.path.lexists(destination):
            raise FileExistsError(f"Output file already exists: {destination}")

        # Keep temporary output on the same file system for no-replace publication.
        with TemporaryDirectory(prefix=".doc-lingo-", dir=destination.parent) as directory:
            temporary = Path(directory) / "output.txt"
            with (
                self.source.open("r", encoding="utf-8", newline="") as source,
                temporary.open("w", encoding="utf-8", newline="") as output,
            ):
                if source.read(1) == "\ufeff":
                    output.write("\ufeff")
                else:
                    source.seek(0)
                self._write_paragraphs(source, output, iter(translations))

            # A hard link publishes only complete content and fails if another
            # process creates the destination meanwhile. rename/replace would
            # overwrite an existing file on some supported operating systems.
            os.link(temporary, destination)

    @staticmethod
    def _write_paragraphs(
        source: TextIO, output: TextIO, translations: Iterator[TextSegment]
    ) -> None:
        number = 0
        for block in iter_text_blocks(source):
            output.write(block.prefix)
            if block.text is not None:
                number += 1
                translated = next(translations, None)
                if translated is None or translated.id != str(number):
                    raise SegmentMismatchError(f"Expected translation for segment {number}")
                text = translated.text.rstrip("\r\n")
                source_lines = block.text.splitlines()
                # Reflow collapsed multiline prose in the document adapter,
                # without asking the model to reproduce physical line breaks.
                if len(source_lines) > 1 and "\n" not in text and "\r" not in text:
                    width = max(40, min(100, max(len(line) for line in source_lines)))
                    ending = re.search(r"\r\n|\r|\n", block.text)
                    assert ending is not None
                    text = ending.group().join(
                        textwrap.wrap(
                            text,
                            width=width,
                            break_long_words=False,
                            break_on_hyphens=False,
                            subsequent_indent=" " * len(block.prefix),
                        )
                    )
                output.write(text)
                output.write(block.ending)
        if next(translations, None) is not None:
            raise SegmentMismatchError(f"Unexpected translation after {number} segments")
