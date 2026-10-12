"""Locate simple UTF-8 text blocks without serializing the surrounding XML."""

from dataclasses import dataclass
from xml.parsers import expat

from doc_lingo.documents.models import TextSegment
from doc_lingo.documents.odt.package import OFFICE, OdtPackageError

TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
_FLOW = {f"{OFFICE}|{name}" for name in ("document-content", "body", "text")} | {
    f"{TEXT}|{name}" for name in ("list", "list-item", "list-header")
}


@dataclass(frozen=True)
class OdtBlock:
    """Byte offsets are for XML patching only, never model alignment."""

    segment: TextSegment
    start: int
    end: int
    reason: str | None = None


def text_blocks(content: bytes) -> tuple[OdtBlock, ...]:
    """Index p/h nodes; unsupported contexts and inline children are retained."""
    try:
        content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise OdtPackageError("ODT text editing currently requires UTF-8 XML") from None
    if b"\x00" in content:
        raise OdtPackageError("ODT text editing currently requires UTF-8 XML")
    parser = expat.ParserCreate(namespace_separator="|")
    stack = []
    active = []
    result = []
    number = 0

    def declaration(version, encoding, standalone):
        if encoding and encoding.lower().replace("-", "") != "utf8":
            raise OdtPackageError("ODT text editing currently requires UTF-8 XML")

    def protected(*args):
        for block in active:
            block["complex"] = True

    def start(name, attributes):
        nonlocal number
        protected()
        if name in (f"{TEXT}|p", f"{TEXT}|h"):
            number += 1
            offset = parser.CurrentByteIndex
            quote = None
            while offset < len(content):
                char = content[offset]
                if quote is not None:
                    if char == quote:
                        quote = None
                elif char in (34, 39):
                    quote = char
                elif char == 62:
                    break
                offset += 1
            active.append(
                {
                    "id": str(number),
                    "depth": len(stack),
                    "start": offset + 1,
                    "empty": content[offset - 1 : offset] == b"/",
                    "parts": [],
                    "complex": False,
                    "supported": all(tag in _FLOW for tag in stack),
                    "type": "heading"
                    if name == f"{TEXT}|h"
                    else "list_item"
                    if f"{TEXT}|list-item" in stack
                    else "paragraph",
                }
            )
        stack.append(name)

    def chars(value):
        if active:
            active[-1]["parts"].append(value)

    def end(name):
        stack.pop()
        if active and active[-1]["depth"] == len(stack):
            block = active.pop()
            text = "".join(block["parts"])
            reason = (
                "unsupported_container"
                if not block["supported"]
                else "inline_content"
                if block["complex"]
                else "empty"
                if not text.strip()
                else None
            )
            result.append(
                OdtBlock(
                    TextSegment(block["id"], text, block["type"]),
                    block["start"],
                    block["start"] if block["empty"] else parser.CurrentByteIndex,
                    reason,
                )
            )

    def doctype(*args):
        raise OdtPackageError("XML document type declarations are unsupported")

    parser.XmlDeclHandler = declaration
    parser.StartDoctypeDeclHandler = doctype
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = chars
    parser.CommentHandler = protected
    parser.ProcessingInstructionHandler = protected
    parser.StartCdataSectionHandler = protected
    try:
        parser.Parse(content, True)
    except expat.ExpatError:
        raise OdtPackageError("Malformed ODT XML") from None
    return tuple(sorted(result, key=lambda block: int(block.segment.id)))
