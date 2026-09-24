"""Source-preserving Markdown adapters; no Markdown rendering or normalization."""

import os
import re
from collections.abc import Generator, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory

from markdown_it import MarkdownIt
from markdown_it.rules_block.table import escapedSplit
from markdown_it.rules_inline.state_inline import StateInline

from doc_lingo.documents.errors import SegmentMismatchError
from doc_lingo.documents.models import TextSegment


def _structure(text: str, environment: dict) -> list[tuple]:
    parser = MarkdownIt("commonmark").enable(["table", "strikethrough"])
    result = []
    for token in parser.parse(text, dict(environment)):
        for item in [token, *(token.children or [])]:
            result.append(
                (
                    item.type,
                    item.tag,
                    item.nesting,
                    item.markup,
                    item.attrs,
                    item.content if item.type in ("code_inline", "code_block", "fence") else "",
                )
            )
    return result


@dataclass(frozen=True)
class _MarkdownSegment(TextSegment):
    environment: dict = field(default_factory=dict, repr=False, compare=False)

    def accepts_translation(self, text: str) -> bool:
        """Reject added/lost markup, changed links and broken emphasis boundaries."""
        if self.type == "table_cell" and (
            "\n" in text
            or "\r" in text
            or len(escapedSplit(text)) != 1
            or (text.endswith("\\") and not self.text.endswith("\\"))
        ):
            return False
        return _structure(self.text, self.environment) == _structure(text, self.environment)


@dataclass(frozen=True)
class _Region:
    start: int
    end: int
    segment: TextSegment


def _cell_ranges(line: str) -> list[tuple[int, int]]:
    """Locate cells using the table parser's immediate-backslash escape rule."""
    prefix = re.match(r"^[ \t]*(?:(?:>[ \t]?|(?:[-+*]|\d+[.)])[ \t]+)[ \t]*)*", line)
    assert prefix is not None
    start = prefix.end()
    end = len(line.rstrip())
    boundaries = [start - 1]
    boundaries.extend(
        i for i in range(start, end) if line[i] == "|" and (i == start or line[i - 1] != "\\")
    )
    boundaries.append(end)
    cells = list(zip((i + 1 for i in boundaries[:-1]), boundaries[1:], strict=True))
    if cells and cells[0][0] == cells[0][1]:
        cells.pop(0)
    if cells and cells[-1][0] == cells[-1][1]:
        cells.pop()
    return [
        (a + len(line[a:b]) - len(line[a:b].lstrip()), b - len(line[a:b]) + len(line[a:b].rstrip()))
        for a, b in cells
    ]


def _inline_ranges(text: str, environment: dict) -> list[tuple[int, int]]:
    """Record consumed syntax using parser rules, including nested link labels.

    Inline tokens have no source offsets. Wrapping the parser's rule API retains
    exact spelling instead of reconstructing escapes, entities or destinations.
    Images and implicit reference labels are deliberately preserved in full.
    """
    parser = MarkdownIt("commonmark").enable("strikethrough")
    ranges: list[tuple[int, int]] = []

    def instrument(name, rule):
        def wrapped(state: StateInline, silent: bool) -> bool:
            start = state.pos
            label_end = -1
            if name == "link" and state.src[start : start + 1] == "[":
                label_end = state.md.helpers.parseLinkLabel(state, start, True)
            matched = rule(state, silent)
            if matched and not silent and state.src is text and name != "text":
                end = state.pos
                if name == "link" and state.src[label_end + 1 : end] not in ("", "[]"):
                    ranges.extend(((start, start + 1), (label_end, end)))
                else:
                    # Hard-break spaces are consumed from pending text by the
                    # newline rule, so include them in its protected range.
                    if name == "newline":
                        while start > 0 and text[start - 1] in " \t":
                            start -= 1
                    ranges.append((start, end))
            return matched

        return wrapped

    names = parser.get_active_rules()["inline"]
    rules = parser.inline.ruler.getRules("")
    for name, rule in zip(names, rules, strict=True):
        parser.inline.ruler.at(name, instrument(name, rule))
    parser.inline.parse(text, parser, environment, [])
    return ranges


def _regions(source: str) -> Iterator[_Region]:
    """Parse once; yield one heading or paragraph (including list continuations).

    Markdown requires document-wide reference resolution. This initial adapter
    holds source and parser tokens in memory, but translations are consumed lazily.
    """
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    parser = MarkdownIt("commonmark").enable(["table", "strikethrough"])
    environment: dict = {}
    tokens = parser.parse(source, environment)
    ignored_until = 0
    if lines and lines[0].strip() == "---":
        # YAML metadata is not prose. An unclosed header is retained in full.
        ignored_until = len(lines)
        for index, line in enumerate(lines[1:], 1):
            if line.strip() in ("---", "..."):
                ignored_until = index + 1
                break
    stack = []
    number = 0
    column = 0
    for token in tokens:
        if token.type == "tr_open":
            column = 0
        if token.nesting == 1:
            stack.append(token.type)
        elif token.nesting == -1:
            stack.pop()
        if token.type != "inline" or token.map is None:
            continue
        in_table = "table_open" in stack
        cell_column = column
        if in_table:
            column += 1
        first, last = token.map
        if first < ignored_until or any(t.type == "html_inline" for t in token.children or []):
            continue
        raw = "".join(lines[first:last])
        region_start, region_end = offsets[first], offsets[last]
        content = token.content
        if in_table:
            cells = _cell_ranges(raw)
            if cell_column >= len(cells):
                continue  # Parser-generated missing cells have no source text.
            a, b = cells[cell_column]
            raw = raw[a:b]
            if not raw or raw.replace("\\|", "|") != content:
                continue  # Do not guess offsets after unsupported normalization.
            region_start, region_end = offsets[first] + a, offsets[first] + b
            content = raw
        # Map normalized inline content back to its original source spelling.
        # Ambiguous normalization (e.g. expanded tabs) is kept unchanged.
        mapping = []
        cursor = 0
        content_lines = [] if in_table else content.split("\n")
        if in_table:
            mapping = list(range(len(raw)))
        for index, part in enumerate(content_lines):
            if first + index >= last:
                break
            line = lines[first + index]
            suffix = r"[ \t]*(?:#+[ \t]*)?" if "heading_open" in stack else r"[ \t]*"
            positions = [
                match.start()
                for match in re.finditer(re.escape(part), line.rstrip("\r\n"))
                if re.fullmatch(suffix, line.rstrip("\r\n")[match.end() :])
            ]
            if not positions:
                break
            position = positions[0]
            mapping.extend(range(cursor + position, cursor + position + len(part)))
            if index < len(content_lines) - 1:
                mapping.append(cursor + len(line.rstrip("\r\n")))
            cursor += len(line)
        if len(mapping) != len(content):
            continue
        editable = set(mapping)
        for start, end in _inline_ranges(content, environment):
            editable.difference_update(mapping[start:end])
        # Physical line endings and outer syntax belong to the document adapter.
        editable = {i for i in editable if raw[i] not in "\r\n"}
        if not any(raw[i].isalnum() for i in editable):
            continue
        protected = []
        position = 0
        while position < len(raw):
            if position in editable:
                position += 1
                continue
            start = position
            while position < len(raw) and position not in editable:
                position += 1
            protected.append((start, position))
        kind = "paragraph"
        if in_table:
            kind = "table_cell"
        elif "heading_open" in stack:
            kind = "heading"
        elif "list_item_open" in stack:
            lists = [item for item in stack if item in ("ordered_list_open", "bullet_list_open")]
            kind = "numbered_item" if lists[-1] == "ordered_list_open" else "bullet_item"
        elif "blockquote_open" in stack:
            kind = "blockquote"
        number += 1
        yield _Region(
            region_start,
            region_end,
            _MarkdownSegment(str(number), raw, kind, tuple(protected), environment),
        )


class MarkdownReader:
    """Extract ordered Markdown text; preserve unsupported constructs verbatim."""

    def __init__(self, source: str | Path) -> None:
        self.source = Path(source)

    @contextmanager
    def iter_segments(self) -> Generator[Iterator[TextSegment], None, None]:
        with self.source.open(encoding="utf-8-sig", newline="") as stream:
            segments = (region.segment for region in _regions(stream.read()))
            try:
                yield segments
            finally:
                segments.close()


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
                    if not region.segment.accepts_translation(segment.text):
                        raise SegmentMismatchError("Translation changes Markdown structure")
                    output.write(source[cursor : region.start])
                    output.write(segment.text)
                    cursor = region.end
                if next(translated, None) is not None:
                    raise SegmentMismatchError("Unexpected extra Markdown translation")
                output.write(source[cursor:])
            os.link(temporary, destination)
