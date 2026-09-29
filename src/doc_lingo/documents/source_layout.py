"""Source coordinates for extracting text without inline wrappers.

These values describe source text only. They neither locate translated words nor
replace the current adapters' syntax protection and validation.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceRange:
    """Outer syntax and inner content as half-open Python string offsets.

    Offsets refer to the same unchanged source string, not bytes or target text.
    The original string owns the delimiters; they are not copied into this value.
    Empty inner ranges are permitted, for example for an empty HTML element.
    """

    outer_start: int
    inner_start: int
    inner_end: int
    outer_end: int

    def __post_init__(self) -> None:
        if not 0 <= self.outer_start <= self.inner_start <= self.inner_end <= self.outer_end:
            raise ValueError("Source range boundaries must be ordered and nonnegative")
        if self.outer_start == self.outer_end:
            raise ValueError("The outer source range must not be empty")


@dataclass(frozen=True)
class SourceLayout:
    """An immutable source and its disjoint or nested inline ranges.

    Ranges are supplied in source order, parents before children. A child must
    fit entirely inside its parent's inner content: crossing ranges and ranges
    inside syntax are invalid. Positions identify repeated text unambiguously.
    This is an opt-in extraction building block, not a Markdown/HTML parser.
    """

    source: str
    ranges: tuple[SourceRange, ...] = ()

    def __post_init__(self) -> None:
        parents: list[SourceRange] = []
        previous_start = -1
        seen: set[SourceRange] = set()
        for item in self.ranges:
            if item.outer_end > len(self.source):
                raise ValueError("Source range exceeds the source length")
            if item.outer_start < previous_start or item in seen:
                raise ValueError("Source ranges must be unique and in source order")
            while parents and item.outer_start >= parents[-1].outer_end:
                parents.pop()
            if parents:
                parent = parents[-1]
                if not parent.inner_start <= item.outer_start < item.outer_end <= parent.inner_end:
                    raise ValueError("Nested source ranges must lie inside parent content")
            parents.append(item)
            previous_start = item.outer_start
            seen.add(item)

    def extract_text(self) -> str:
        """Remove recorded wrappers while preserving all remaining characters.

        Nested wrappers are removed once; links retain their labels rather than
        their destinations. This does not decode entities/escapes, normalize
        whitespace, or determine whether content such as code is translatable.
        Those decisions belong to the format adapter. No target offsets are
        inferred from these source coordinates.
        """
        wrappers = sorted(
            boundary
            for item in self.ranges
            for boundary in (
                (item.outer_start, item.inner_start),
                (item.inner_end, item.outer_end),
            )
            if boundary[0] < boundary[1]
        )
        parts: list[str] = []
        cursor = 0
        for start, end in wrappers:
            parts.append(self.source[cursor:start])
            cursor = end
        parts.append(self.source[cursor:])
        return "".join(parts)
