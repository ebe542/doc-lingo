"""Read simple main-body ODT paragraphs, headings and list paragraphs."""

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path

from doc_lingo.documents.models import TextSegment
from doc_lingo.documents.odt.blocks import OdtBlock, text_blocks
from doc_lingo.documents.odt.package import inspect_package
from doc_lingo.documents.odt.styles import language_only_styles


class OdtReader:
    def __init__(self, source: str | Path):
        self.source = Path(source)
        self.skipped_blocks: tuple[OdtBlock, ...] = ()

    @contextmanager
    def iter_segments(self) -> Generator[Iterator[TextSegment], None, None]:
        self.skipped_blocks = ()
        package = inspect_package(self.source)
        blocks = text_blocks(package.content_xml, language_styles=language_only_styles(package))
        self.skipped_blocks = tuple(block for block in blocks if block.reason is not None)
        segments = (block.segment for block in blocks if block.reason is None)
        try:
            yield segments
        finally:
            segments.close()
