"""Locate supported UTF-8 text blocks and preserve original inline XML."""

from dataclasses import dataclass, replace
from xml.parsers import expat

from doc_lingo.documents.models import TextSegment
from doc_lingo.documents.odt.inline import inline_segment
from doc_lingo.documents.odt.package import OFFICE, OdtPackageError, OdtPackageInfo
from doc_lingo.documents.odt.styles import language_only_styles, preformatted_styles

TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
DRAW = "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
STYLE = "urn:oasis:names:tc:opendocument:xmlns:style:1.0"
TABLE = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
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
_FLOW = (
    {f"{OFFICE}|{name}" for name in ("document-content", "body", "text")}
    | {f"{TEXT}|{name}" for name in ("list", "list-item", "list-header")}
    | {
        f"{TABLE}|{name}"
        for name in (
            "table",
            "table-header-rows",
            "table-rows",
            "table-row-group",
            "table-row",
            "table-cell",
        )
    }
)


@dataclass(frozen=True)
class OdtBlock:
    """Byte offsets are for XML patching only, never model alignment."""

    segment: TextSegment
    start: int
    end: int
    reason: str | None = None
    frames: tuple[tuple[int, int], ...] = ()
    part: str = "content.xml"


def _supported_context(stack: list[str], part: str) -> bool:
    """Allow textbox flow, including paragraph-owned frames, but no unknown wrappers."""
    if part == "styles.xml":
        prefix = [f"{OFFICE}|document-styles", f"{OFFICE}|master-styles", f"{STYLE}|master-page"]
        regions = {
            f"{STYLE}|{name}"
            for name in (
                "header",
                "header-left",
                "header-first",
                "footer",
                "footer-left",
                "footer-first",
            )
        }
        if stack[:3] != prefix or len(stack) < 4 or stack[3] not in regions:
            return False
        stack = stack[4:]
    wrappers = _WRAPPERS | {f"{TEXT}|p", f"{TEXT}|h"}
    for index, tag in enumerate(stack):
        if tag in _FLOW:
            continue
        if tag == f"{DRAW}|text-box" and index and stack[index - 1] == f"{DRAW}|frame":
            continue
        if tag == f"{DRAW}|frame" and stack[index + 1 : index + 2] == [f"{DRAW}|text-box"]:
            continue
        if tag in wrappers:
            following = index + 1
            while following < len(stack) and stack[following] in _WRAPPERS:
                following += 1
            if stack[following : following + 2] == [f"{DRAW}|frame", f"{DRAW}|text-box"]:
                continue
        return False
    return True


def package_blocks(package: OdtPackageInfo) -> tuple[OdtBlock, ...]:
    """Use identical package-wide style policies for reading, writing and inventory."""
    blocks = []
    language_styles = language_only_styles(package)
    protected_styles = preformatted_styles(package)
    for part, xml in package_parts(package).items():
        blocks.extend(
            text_blocks(
                xml,
                part=part,
                language_styles=language_styles,
                protected_styles=protected_styles,
            )
        )
    return tuple(blocks)


def package_parts(package: OdtPackageInfo) -> dict[str, bytes]:
    """Editable XML parts in stable translation order."""
    parts = {"content.xml": package.content_xml}
    if package.styles_xml is not None:
        parts["styles.xml"] = package.styles_xml
    return parts


def text_blocks(
    content: bytes,
    *,
    part: str = "content.xml",
    language_styles: frozenset[str] = frozenset(),
    protected_styles: frozenset[str] = frozenset(),
) -> tuple[OdtBlock, ...]:
    """Index p/h nodes; unsupported contexts and inline constructs are retained."""
    try:
        content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise OdtPackageError("ODT text editing currently requires UTF-8 XML") from None
    if b"\x00" in content:
        raise OdtPackageError("ODT text editing currently requires UTF-8 XML")
    parser = expat.ParserCreate(namespace_separator="|")
    stack = []
    value_cells = []
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
        if name == f"{TABLE}|table-cell" and (
            f"{TABLE}|formula" in attributes
            or attributes.get(f"{OFFICE}|value-type", "string") != "string"
            or any(
                f"{OFFICE}|{key}" in attributes
                for key in ("value", "date-value", "time-value", "boolean-value", "string-value")
            )
        ):
            value_cells.append(len(stack))
        for parent in active:
            if parent["opaque"] is not None:
                continue
            if name in _WRAPPERS:
                if (
                    name == f"{TEXT}|span"
                    and set(attributes) == {f"{TEXT}|style-name"}
                    and attributes[f"{TEXT}|style-name"] in language_styles
                ):
                    parent["neutral"].add(left)
                parent["tokens"].append((left, right))
                if not empty:
                    parent["wrappers"][len(stack)] = (left, right)
            elif name in _OPAQUE:
                if name in {f"{TEXT}|page-number", f"{TEXT}|page-count", f"{TEXT}|sequence"}:
                    parent["has_field"] = True
                if name == f"{DRAW}|frame":
                    parent["frames"].add(left)
                if empty:
                    parent["tokens"].append((left, right))
                else:
                    parent["opaque"] = (len(stack), left)
            else:
                parent["complex"] = True
        if name in (f"{TEXT}|p", f"{TEXT}|h"):
            number += 1
            textbox_boundary = max(
                (i + 1 for i, tag in enumerate(stack) if tag == f"{DRAW}|text-box"), default=0
            )
            active.append(
                {
                    "id": str(number),
                    "depth": len(stack),
                    "start": right,
                    "empty": empty,
                    "tokens": [],
                    "wrappers": {},
                    "ranges": [],
                    "neutral": set(),
                    "frames": set(),
                    "opaque": None,
                    "parts": [],
                    "complex": False,
                    "has_field": False,
                    "supported": _supported_context(stack, part),
                    "value_cell": bool(value_cells),
                    "preformatted": attributes.get(f"{TEXT}|style-name") in protected_styles
                    or any(parent["preformatted"] for parent in active),
                    "type": "heading"
                    if name == f"{TEXT}|h"
                    else "list_item"
                    if f"{TEXT}|list-item" in stack[textbox_boundary:]
                    else "paragraph",
                }
            )
        stack.append(name)

    def chars(value):
        if active:
            active[-1]["parts"].append(value)

    def end(name):
        stack.pop()
        if value_cells and value_cells[-1] == len(stack):
            value_cells.pop()
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
                "protected_preformatted"
                if block["preformatted"]
                else "unsupported_container"
                if not block["supported"]
                else "unsupported_cell_value"
                if block["value_cell"]
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
                    block["neutral"],
                    block["frames"],
                )
                if not segment.accepts_translation(segment.text):
                    reason = "protected_only"
                elif block["has_field"]:
                    # Only field-bearing blocks qualify. Do not suppress ordinary
                    # punctuation paragraphs or prose wrapped in text:span.
                    cursor = 0
                    prose = []
                    for left, right in segment.protected_spans:
                        prose.append(segment.text[cursor:left])
                        cursor = right
                    prose.append(segment.text[cursor:])
                    if all(c.isspace() or c in "/|:;.,-–—()[]{}" for c in "".join(prose)):
                        reason = "protected_only"
            result.append(
                OdtBlock(
                    segment,
                    block["start"],
                    end_offset,
                    reason,
                    tuple((a, b) for a, b in block["tokens"] if a in block["frames"]),
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
    ordered = sorted(result, key=lambda block: int(block.segment.id))
    return tuple(
        replace(
            block,
            part=part,
            segment=replace(
                block.segment,
                id=block.segment.id if part == "content.xml" else f"{part}:{block.segment.id}",
            ),
        )
        for block in ordered
    )
