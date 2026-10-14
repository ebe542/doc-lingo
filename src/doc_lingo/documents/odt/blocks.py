"""Locate supported UTF-8 text blocks and preserve original inline XML."""

from dataclasses import dataclass
from xml.parsers import expat

from doc_lingo.documents.models import TextSegment
from doc_lingo.documents.odt.inline import inline_segment
from doc_lingo.documents.odt.package import OFFICE, OdtPackageError

TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
DRAW = "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
_WRAPPERS = {f"{TEXT}|span", f"{TEXT}|a"}
_OPAQUE = {
    f"{TEXT}|{name}"
    for name in (
        "s",
        "tab",
        "line-break",
        "bookmark",
        "bookmark-start",
        "bookmark-end",
        "page-number",
        "page-count",
        "sequence",
        "soft-page-break",
    )
} | {f"{DRAW}|frame"}
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
    """Index p/h nodes; unsupported contexts and inline constructs are retained."""
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

    def tag_end(offset):
        quote = None
        while offset < len(content):
            char = content[offset]
            if quote is not None:
                if char == quote:
                    quote = None
            elif char in (34, 39):
                quote = char
            elif char == 62:
                return offset + 1
            offset += 1
        raise OdtPackageError("Unterminated ODT XML tag")

    def declaration(version, encoding, standalone):
        if encoding and encoding.lower().replace("-", "") != "utf8":
            raise OdtPackageError("ODT text editing currently requires UTF-8 XML")

    def protected(*args):
        for block in active:
            if block["opaque"] is None:
                block["complex"] = True

    def start(name, attributes):
        nonlocal number
        left = parser.CurrentByteIndex
        right = tag_end(left)
        empty = content[right - 2 : right] == b"/>"
        for parent in active:
            if parent["opaque"] is not None:
                continue
            if name in _WRAPPERS:
                parent["tokens"].append((left, right))
                if not empty:
                    parent["wrappers"][len(stack)] = (left, right)
            elif name in _OPAQUE:
                if empty:
                    parent["tokens"].append((left, right))
                else:
                    parent["opaque"] = (len(stack), left)
            else:
                parent["complex"] = True
        if name in (f"{TEXT}|p", f"{TEXT}|h"):
            number += 1
            active.append(
                {
                    "id": str(number),
                    "depth": len(stack),
                    "start": right,
                    "empty": empty,
                    "tokens": [],
                    "wrappers": {},
                    "ranges": [],
                    "opaque": None,
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
        for parent in active:
            opaque = parent["opaque"]
            if opaque is not None and opaque[0] == len(stack):
                parent["tokens"].append((opaque[1], tag_end(parser.CurrentByteIndex)))
                parent["opaque"] = None
            elif opaque is None and len(stack) in parent["wrappers"]:
                parent["tokens"].append((parser.CurrentByteIndex, tag_end(parser.CurrentByteIndex)))
                opening = parent["wrappers"].pop(len(stack))
                parent["ranges"].append(
                    (*opening, parser.CurrentByteIndex, tag_end(parser.CurrentByteIndex))
                )
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
            end_offset = block["start"] if block["empty"] else parser.CurrentByteIndex
            segment = TextSegment(block["id"], text, block["type"])
            if reason is None and block["tokens"]:
                segment = inline_segment(
                    block["id"],
                    block["type"],
                    content,
                    block["start"],
                    end_offset,
                    block["tokens"],
                    block["ranges"],
                )
                if not segment.accepts_translation(segment.text):
                    reason = "protected_only"
            result.append(
                OdtBlock(
                    segment,
                    block["start"],
                    end_offset,
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
