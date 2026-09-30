"""Shared incremental TXT boundaries for extraction and reconstruction."""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TextIO

_LIST_ITEM = re.compile(
    r"^(?P<prefix>[ \t]*(?:(?P<bullet>[-*\u2022])|(?P<number>[0-9]+[.)]))[ \t]+)"
    r"(?P<text>\S.*)$"
)
_BULLET_ITEM = "bullet_item"
_NUMBERED_ITEM = "numbered_item"


@dataclass(frozen=True)
class TextBlock:
    """Adapter-owned formatting and optional translatable content."""

    prefix: str
    text: str | None
    type: str = "paragraph"
    ending: str = ""


def iter_text_blocks(source: TextIO) -> Iterator[TextBlock]:
    """Yield prose paragraphs, complete list items, and untouched blank lines.

    List markers require following whitespace and nonblank text. Unmarked lines
    continue the active item, regardless of indentation, until a blank line,
    another marker, or EOF. Nesting is not interpreted.
    Reader and writer share this function so their segment IDs cannot drift.
    """
    lines: list[str] = []
    prefix = ""
    segment_type = "paragraph"
    iterator = iter(source)
    line = next(iterator, None)
    while line is not None:
        following = next(iterator, None)
        body = line.rstrip("\r\n")
        ending = line[len(body) :]
        item = _LIST_ITEM.fullmatch(body)
        # TXT has no heading syntax. Recognize short standalone labels only
        # before substantial prose and outside an active list item.
        previous_complete = not lines or lines[-1].rstrip().endswith((".", "!", "?"))
        heading = (
            segment_type == "paragraph"
            and previous_complete
            and 0 < len(body.split()) <= 6
            and len(body) <= 60
            and body[:1].isupper()
            and body[-1:] not in ".,;!?"
            and following is not None
            and len(following.split()) >= 10
            and _LIST_ITEM.fullmatch(following.rstrip("\r\n")) is None
        )
        if not line.strip() or item or heading:
            if lines:
                text = "".join(lines)
                lines.clear()
                yield TextBlock(
                    prefix=prefix,
                    text=text,
                    type=segment_type,
                    ending=text[len(text.rstrip("\r\n")) :],
                )
            if heading:
                yield TextBlock("", line, "heading", ending)
                prefix = ""
                segment_type = "paragraph"
            elif item:
                prefix = item.group("prefix")
                segment_type = _BULLET_ITEM if item.group("bullet") else _NUMBERED_ITEM
                lines.append(item.group("text") + ending)
            else:
                prefix = ""
                segment_type = "paragraph"
                yield TextBlock(line, None)
        else:
            lines.append(line)
        line = following
    if lines:
        text = "".join(lines)
        yield TextBlock(
            prefix=prefix,
            text=text,
            type=segment_type,
            ending=text[len(text.rstrip("\r\n")) :],
        )
