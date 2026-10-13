"""Patch supported text blocks while preserving every other member's payload."""

import os
from collections.abc import Iterable
from copy import copy
from pathlib import Path
from shutil import copyfileobj
from tempfile import TemporaryDirectory
from xml.sax.saxutils import escape
from zipfile import ZipFile

from doc_lingo.documents.errors import SegmentMismatchError
from doc_lingo.documents.models import TextSegment
from doc_lingo.documents.odt.blocks import text_blocks
from doc_lingo.documents.odt.inline import OdtInlineSegment
from doc_lingo.documents.odt.package import OdtPackageError, inspect_package


class OdtWriter:
    def __init__(self, source: str | Path):
        self.source = Path(source)

    def write(self, destination: Path, translations: Iterable[TextSegment]) -> None:
        destination = Path(destination)
        if os.path.lexists(destination):
            raise FileExistsError(f"Output file already exists: {destination}")
        package = inspect_package(self.source)
        blocks = text_blocks(package.content_xml)
        values = iter(translations)
        pieces = []
        cursor = 0
        for block in blocks:
            if block.reason is not None:
                continue
            value = next(values, None)
            if value is None or value.id != block.segment.id or value.type != block.segment.type:
                raise SegmentMismatchError("ODT translations must match source IDs and types")
            replacement = package.content_xml[block.start : block.end]
            if value.text != block.segment.text and isinstance(block.segment, OdtInlineSegment):
                replacement = block.segment.render(value.text)
            elif value.text != block.segment.text:
                if not value.text.strip() or any(
                    not (
                        c in "\t\n\r"
                        or 0x20 <= ord(c) <= 0xD7FF
                        or 0xE000 <= ord(c) <= 0xFFFD
                        or 0x10000 <= ord(c) <= 0x10FFFF
                    )
                    for c in value.text
                ):
                    raise OdtPackageError("Invalid or empty translated ODT text")
                # This first subset cannot express changed explicit whitespace.
                if any(c in value.text for c in "\t\n\r") or "  " in value.text:
                    raise OdtPackageError("Changed ODT whitespace requires inline support")
                replacement = escape(value.text).encode("utf-8")
            pieces.extend((package.content_xml[cursor : block.start], replacement))
            cursor = block.end
        if next(values, None) is not None:
            raise SegmentMismatchError("Unexpected extra ODT translation")
        pieces.append(package.content_xml[cursor:])
        content = b"".join(pieces)
        with TemporaryDirectory(prefix=".doc-lingo-", dir=destination.parent) as directory:
            temporary = Path(directory) / "output.odt"
            with ZipFile(self.source) as source, ZipFile(temporary, "w") as output:
                if source.read("content.xml") != package.content_xml:
                    raise OdtPackageError("ODT source changed during writing")
                output.comment = source.comment
                for member in source.infolist():
                    if member.filename == "content.xml":
                        output.writestr(copy(member), content)
                    else:
                        with (
                            source.open(member) as incoming,
                            output.open(copy(member), "w") as outgoing,
                        ):
                            copyfileobj(incoming, outgoing)
            inspect_package(temporary)
            os.link(temporary, destination)
