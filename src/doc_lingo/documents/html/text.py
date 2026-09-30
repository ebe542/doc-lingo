"""Locate visible HTML text without serializing or normalizing the source."""

import re
from dataclasses import dataclass, replace
from html import unescape
from html.parser import HTMLParser

from doc_lingo.documents.models import TextSegment
from doc_lingo.documents.source_layout import SourceLayout, SourceRange

_VOID = frozenset(
    [
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    ]
)
_EXCLUDED = frozenset(["script", "style", "pre", "code", "head", "template"])
_BLOCK = frozenset(
    [
        "address",
        "article",
        "aside",
        "blockquote",
        "div",
        "dl",
        "dt",
        "dd",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "section",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    ]
)
HtmlContext = tuple[tuple[str, bool], ...]


@dataclass
class _Element:
    tag: str
    has_attributes: bool
    start: int
    opening_end: int
    closing_start: int | None = None
    end: int | None = None
    excluded: bool = False


class HtmlText(HTMLParser):
    """Record data offsets, block boundaries and exact non-text source events.

    Context travels between Markdown tokens because an HTML element may span
    blank lines and multiple Markdown blocks. Opaque Markdown syntax is masked
    before parsing so tags inside code or link destinations cannot affect HTML.
    This is a conservative tokenizer, not a browser DOM or CSS visibility engine.
    """

    def __init__(
        self, source: str, context: HtmlContext = (), opaque: tuple[tuple[int, int], ...] = ()
    ) -> None:
        super().__init__(convert_charrefs=False)
        self.source = source
        self.elements = list(context)
        self.text_present: list[bool] = []
        self.locations: list[_Element] = []
        self.text_stack: list[int | None] = [None] * len(context)
        self.editable: set[int] = set()
        self.cuts = {0, len(source)}
        self.signature: list[tuple[str, str]] = []
        self.safe = True
        self.offsets = [0]
        self.offsets.extend(i + 1 for i, char in enumerate(source) if char == "\n")
        masked = list(source)
        for start, end in opaque:
            for i in range(start, end):
                if masked[i] not in "\r\n":
                    masked[i] = " "
        try:
            self.feed("".join(masked))
            self.close()
        except (AssertionError, ValueError):
            # HTMLParser rejects some malformed declarations rather than
            # reporting them through a callback. Retain those fragments too.
            self.safe = False
        # Open elements may span Markdown fragments. Propagate descendant text
        # without requiring the fragment to close all of its inherited elements.
        for child, parent in zip(self.text_stack[:0:-1], self.text_stack[-2::-1], strict=True):
            if child is not None and parent is not None and self.text_present[child]:
                self.text_present[parent] = True

    def validation_errors(self, original: "HtmlText") -> tuple[str, ...]:
        errors = []
        if not original.safe:
            errors.append("html_source_unparseable")
        if not self.safe:
            errors.append("html_translation_unparseable")
        if original.signature != self.signature:
            errors.append("html_tags_attributes_or_protected_content_changed")
        if original.context != self.context:
            errors.append("html_element_stack_changed")
        if len(original.text_present) != len(self.text_present):
            errors.append("html_element_count_changed")
        else:
            errors.extend(
                f"html_text_emptied: {original.locations[i].tag}[{i}]"
                for i, (before, after) in enumerate(
                    zip(original.text_present, self.text_present, strict=True)
                )
                if before and not after
            )
        return tuple(errors)

    def source_layout(self) -> SourceLayout:
        """Expose complete, editable elements; retain excluded or open syntax."""
        if not self.safe:
            return SourceLayout(self.source)
        return SourceLayout(
            self.source,
            tuple(
                SourceRange(item.start, item.opening_end, item.closing_start, item.end)
                for item in self.locations
                if not item.excluded and item.closing_start is not None and item.end is not None
            ),
        )

    def _mark_text(self, text: str) -> None:
        index = self.text_stack[-1] if self.text_stack else None
        if text.strip() and index is not None:
            self.text_present[index] = True

    @property
    def context(self) -> HtmlContext:
        return tuple(self.elements)

    def _position(self) -> int:
        line, column = self.getpos()
        return self.offsets[line - 1] + column

    def _record(self, kind: str, length: int) -> None:
        start = self._position()
        self.signature.append((kind, self.source[start : start + length]))

    def _tag(self, tag: str, length: int) -> None:
        self._record("tag", length)
        if tag in _BLOCK:
            start = self._position()
            self.cuts.update((start, start + length))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        raw = self.get_starttag_text()
        assert raw is not None
        self._tag(tag, len(raw))
        excluded = bool(self.elements and self.elements[-1][1]) or tag in _EXCLUDED
        excluded |= any(
            (name == "translate" and (value or "").strip().lower() == "no") or name == "hidden"
            for name, value in attrs
        )
        if tag not in _VOID:
            self.elements.append((tag, excluded))
            self.text_stack.append(len(self.text_present))
            self.text_present.append(False)
            self.locations.append(
                _Element(
                    tag,
                    bool(attrs),
                    self._position(),
                    self._position() + len(raw),
                    excluded=excluded,
                )
            )

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        raw = self.get_starttag_text()
        assert raw is not None
        self._tag(tag, len(raw))

    def handle_endtag(self, tag: str) -> None:
        start = self._position()
        end = self.source.find(">", start) + 1
        self._tag(tag, end - start)
        if not self.elements or self.elements[-1][0] != tag:
            # Do not repair mismatched/implicitly closed HTML. The affected
            # fragment is retained and context stays conservative for followers.
            self.safe = False
            return
        self.elements.pop()
        index = self.text_stack.pop()
        if index is not None:
            self.locations[index].closing_start = start
            self.locations[index].end = end
        if index is not None and self.text_present[index]:
            self._mark_text("content")

    def handle_data(self, data: str) -> None:
        if self.elements and self.elements[-1][1]:
            self._record("excluded", len(data))
        else:
            start = self._position()
            self._mark_text(data)
            if data.startswith("<") and re.match(r"<[A-Za-z/!?]", self.source[start:]):
                # close() can expose unfinished tags/comments as ordinary data.
                # Do not send that syntax or comment content to the translator.
                self.safe = False
            self.editable.update(range(start, start + len(data)))

    def handle_entityref(self, name: str) -> None:
        start = self._position()
        length = len(name) + 1
        length += self.source[start + length : start + length + 1] == ";"
        self._record("entity", length)
        if not self.elements or not self.elements[-1][1]:
            self._mark_text(unescape(self.source[start : start + length]))

    def handle_charref(self, name: str) -> None:
        self.handle_entityref("#" + name)

    def handle_comment(self, data: str) -> None:
        start = self._position()
        end = self.source.find("-->", start)
        # Some Python versions deliver unsupported declarations through this
        # callback as bogus comments instead of unknown_decl() or an exception.
        # Validate source spelling before recording an exact comment range.
        if not self.source.startswith("<!--", start) or end < 0:
            self.safe = False
            return
        self._record("comment", end + 3 - start)

    def handle_decl(self, decl: str) -> None:
        self._record("declaration", len(decl) + 3)

    def handle_pi(self, data: str) -> None:
        self._record("instruction", len(data) + 3)

    def unknown_decl(self, data: str) -> None:
        self.safe = False


def remove_empty_emphasis(original: HtmlText, translated: HtmlText) -> tuple[str, str] | None:
    """Remove only newly emptied, closed, attribute-free emphasis tag pairs.

    Return a matching source baseline for full adapter validation. Missing or
    changed tags are never repaired here; all other protection remains strict.
    """
    if (
        not original.safe
        or not translated.safe
        or original.signature != translated.signature
        or original.context != translated.context
        or len(original.locations) != len(translated.locations)
    ):
        return None
    lost = [
        i
        for i, (before, after) in enumerate(
            zip(original.text_present, translated.text_present, strict=True)
        )
        if before and not after
    ]
    if not lost:
        return None
    source_ranges = []
    output_ranges = []
    for index in lost:
        for layout, ranges in ((original, source_ranges), (translated, output_ranges)):
            item = layout.locations[index]
            if (
                item.tag not in {"strong", "em", "b", "i"}
                or item.has_attributes
                or item.closing_start is None
                or item.end is None
            ):
                return None
            ranges.extend(((item.start, item.opening_end), (item.closing_start, item.end)))
    # Empty nested emphasis can be removed together, but comments, entities,
    # images or other elements inside a candidate must not be discarded.
    removed = {i for start, end in output_ranges for i in range(start, end)}
    for index in lost:
        item = translated.locations[index]
        assert item.closing_start is not None
        if any(
            not translated.source[i].isspace() and i not in removed
            for i in range(item.opening_end, item.closing_start)
        ):
            return None

    def strip_tags(text: str, ranges: list[tuple[int, int]]) -> str:
        pieces = []
        cursor = 0
        for start, end in sorted(ranges):
            pieces.append(text[cursor:start])
            cursor = end
        return "".join(pieces) + text[cursor:]

    return strip_tags(original.source, source_ranges), strip_tags(translated.source, output_ranges)


def protected_ranges(text: str, editable: set[int]) -> tuple[tuple[int, int], ...]:
    """Retain outer whitespace and line endings as well as parser-owned syntax."""
    first = len(text) - len(text.lstrip())
    last = len(text.rstrip())
    allowed = {i for i in editable if first <= i < last and text[i] not in "\r\n"}
    ranges = []
    position = 0
    while position < len(text):
        if position in allowed:
            position += 1
            continue
        start = position
        while position < len(text) and position not in allowed:
            position += 1
        ranges.append((start, position))
    return tuple(ranges)


@dataclass(frozen=True)
class HtmlSegment(TextSegment):
    """A raw HTML text run; block tags remain outside its replacement range."""

    def source_layout(self) -> SourceLayout:
        return HtmlText(self.text).source_layout()

    def repair_translation(self, text: str) -> str | None:
        repair = remove_empty_emphasis(HtmlText(self.text), HtmlText(text))
        if repair is not None:
            baseline, repaired = repair
            if replace(self, text=baseline, protected_spans=()).accepts_translation(repaired):
                return repaired
        return None

    def accepts_translation(self, text: str) -> bool:
        return not self.validation_errors(text)

    def validation_errors(self, text: str) -> tuple[str, ...]:
        return HtmlText(text).validation_errors(HtmlText(self.text))
