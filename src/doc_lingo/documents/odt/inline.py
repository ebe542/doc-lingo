"""Conservative inline XML protection using exact source fragments."""

from dataclasses import dataclass
from html import unescape
from xml.sax.saxutils import escape

from doc_lingo.documents.models import TextSegment
from doc_lingo.documents.odt.package import OdtPackageError


@dataclass(frozen=True)
class OdtInlineSegment(TextSegment):
    """Decoded prose interleaved with protected source XML; no word projection yet."""

    def render(self, text: str) -> bytes:
        fragments = [self.text[a:b] for a, b in self.protected_spans]
        cursor = 0
        parts = []
        visible = []
        for fragment in fragments:
            position = text.find(fragment, cursor)
            if position < 0:
                raise OdtPackageError("ODT inline protection changed")
            prose = text[cursor:position]
            if any(item in prose for item in fragments):
                raise OdtPackageError("ODT inline protection changed")
            parts.extend((escape(prose), fragment))
            visible.append(prose)
            cursor = position + len(fragment)
        prose = text[cursor:]
        if any(item in prose for item in fragments):
            raise OdtPackageError("ODT inline protection changed")
        parts.append(escape(prose))
        visible.append(prose)
        if not "".join(visible).strip():
            raise OdtPackageError("Empty translated ODT inline text")
        if any(
            not (
                c in "\t\n\r"
                or 0x20 <= ord(c) <= 0xD7FF
                or 0xE000 <= ord(c) <= 0xFFFD
                or 0x10000 <= ord(c) <= 0x10FFFF
            )
            for c in text
        ):
            raise OdtPackageError("Invalid translated ODT inline text")
        return "".join(parts).encode("utf-8")

    def accepts_translation(self, text: str) -> bool:
        try:
            self.render(text)
        except (OdtPackageError, UnicodeError):
            return False
        return True


def inline_segment(
    identity: str,
    kind: str,
    content: bytes,
    start: int,
    end: int,
    tokens: list[tuple[int, int]],
) -> OdtInlineSegment:
    """Decode XML prose while keeping opaque source byte ranges intact."""

    def decode(prose: bytes) -> str:
        return unescape(prose.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n"))

    pieces = []
    spans = []
    cursor = start
    offset = 0
    for left, right in tokens:
        prose = decode(content[cursor:left])
        fragment = content[left:right].decode("utf-8")
        pieces.extend((prose, fragment))
        offset += len(prose)
        spans.append((offset, offset + len(fragment)))
        offset += len(fragment)
        cursor = right
    pieces.append(decode(content[cursor:end]))
    return OdtInlineSegment(identity, "".join(pieces), kind, tuple(spans))
