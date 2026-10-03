"""Write validated Markdown translations without normalizing source syntax."""

import os
from collections.abc import Iterable
from pathlib import Path
from tempfile import TemporaryDirectory

from doc_lingo.documents.errors import SegmentMismatchError
from doc_lingo.documents.markdown._parser import _regions
from doc_lingo.documents.markdown.aligned import AlignedMarkdownSegment, accepts_aligned
from doc_lingo.documents.models import TextSegment


class MarkdownWriter:
    """Publish validated translations atomically without replacing any output."""

    def __init__(self, source: str | Path) -> None:
        self.source = Path(source)

    def write(self, destination: Path, translations: Iterable[TextSegment]) -> None:
        destination = Path(destination)
        if os.path.lexists(destination):
            raise FileExistsError(f"Output file already exists: {destination}")
        with self.source.open(encoding="utf-8", newline="") as stream:
            original = stream.read()
        bom = "\ufeff" if original.startswith("\ufeff") else ""
        source = original[len(bom) :]
        translated = iter(translations)
        with TemporaryDirectory(prefix=".doc-lingo-", dir=destination.parent) as directory:
            temporary = Path(directory) / "output.md"
            with temporary.open("w", encoding="utf-8", newline="") as output:
                output.write(bom)
                cursor = 0
                for region in _regions(source):
                    segment = next(translated, None)
                    if segment is None or segment.id != region.segment.id:
                        raise SegmentMismatchError(f"Expected segment {region.segment.id}")
                    valid_repair = (
                        segment.unrepaired_text is not None
                        and region.segment.repair_translation(segment.unrepaired_text)
                        == segment.text
                    )
                    valid_alignment = (
                        isinstance(segment, AlignedMarkdownSegment)
                        and segment.restored is not None
                        and accepts_aligned(region.segment, segment)
                    )
                    if (
                        not valid_alignment
                        and not valid_repair
                        and not region.segment.accepts_translation(segment.text)
                    ):
                        raise SegmentMismatchError("Translation changes Markdown structure")
                    output.write(source[cursor : region.start])
                    output.write(segment.text)
                    cursor = region.end
                if next(translated, None) is not None:
                    raise SegmentMismatchError("Unexpected extra Markdown translation")
                output.write(source[cursor:])
            os.link(temporary, destination)
