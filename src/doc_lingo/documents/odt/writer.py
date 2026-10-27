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
from doc_lingo.documents.odt.aligned import AlignedOdtSegment, render_segment
from doc_lingo.documents.odt.blocks import package_blocks, package_parts
from doc_lingo.documents.odt.inline import OdtInlineSegment
from doc_lingo.documents.odt.package import OdtPackageError, inspect_package
from doc_lingo.documents.odt.patches import compose_blocks


class OdtWriter:
    def __init__(self, source: str | Path):
        self.source = Path(source)

    def write(self, destination: Path, translations: Iterable[TextSegment]) -> None:
        destination = Path(destination)
        if os.path.lexists(destination):
            raise FileExistsError(f"Output file already exists: {destination}")
        package = inspect_package(self.source)
        blocks = package_blocks(package)
        parts = package_parts(package)
        values = iter(translations)
        replacements = {}
        for block in blocks:
            if block.reason is not None:
                continue
            value = next(values, None)
            if value is None or value.id != block.segment.id or value.type != block.segment.type:
                raise SegmentMismatchError("ODT translations must match source IDs and types")
            replacement = parts[block.part][block.start : block.end]
            if isinstance(value, AlignedOdtSegment) and value.restored is not None:
                if not isinstance(block.segment, OdtInlineSegment):
                    raise OdtPackageError("ODT alignment requires an inline source")
                rendered, _ = render_segment(block.segment, value.restored)
                if value.text != rendered:
                    raise OdtPackageError("ODT rendered alignment mismatch")
                replacement = rendered.encode("utf-8")
            elif value.text != block.segment.text and isinstance(block.segment, OdtInlineSegment):
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
            replacements[block.segment.id] = replacement
        if next(values, None) is not None:
            raise SegmentMismatchError("Unexpected extra ODT translation")
        rendered_parts = {
            name: compose_blocks(xml, tuple(b for b in blocks if b.part == name), replacements)
            for name, xml in parts.items()
        }
        with TemporaryDirectory(prefix=".doc-lingo-", dir=destination.parent) as directory:
            temporary = Path(directory) / "output.odt"
            with ZipFile(self.source) as source, ZipFile(temporary, "w") as output:
                if any(source.read(name) != xml for name, xml in parts.items()):
                    raise OdtPackageError("ODT source changed during writing")
                output.comment = source.comment
                for member in source.infolist():
                    if member.filename in rendered_parts:
                        output.writestr(copy(member), rendered_parts[member.filename])
                    else:
                        with (
                            source.open(member) as incoming,
                            output.open(copy(member), "w") as outgoing,
                        ):
                            copyfileobj(incoming, outgoing)
            inspect_package(temporary)
            os.link(temporary, destination)
