"""Source-backed input preparation, independent of models and target alignment."""

from dataclasses import dataclass
from typing import Literal

from doc_lingo.documents.source_layout import SourceLayout


@dataclass(frozen=True)
class InputPart:
    """A half-open source slice; text and symbols remain owned by the layout."""

    start: int
    end: int
    kind: Literal["text", "protected", "syntax"]


@dataclass(frozen=True)
class TranslationInput:
    """An intermediate representation, not a backend request.

    Parts partition the original source. Syntax is removable wrapping; protected
    parts retain opaque code, entities and other adapter-owned source verbatim.
    The layout retains formatting relationships, even across sentence boundaries.
    No target positions or markers are generated and no sentence splitting occurs.
    """

    layout: SourceLayout
    parts: tuple[InputPart, ...]

    @classmethod
    def from_layout(
        cls, layout: SourceLayout, protected_spans: tuple[tuple[int, int], ...] = ()
    ) -> "TranslationInput":
        """Partition at source boundaries; known wrappers take precedence.

        Readers currently protect both wrappers and opaque contents. Removing
        only wrappers identified by the layout avoids exposing unrecognized
        syntax as translatable text. Sweep sorted boundaries without allocating
        per-character masks, including for very large paragraphs.
        """
        previous = 0
        for start, end in protected_spans:
            if not previous <= start < end <= len(layout.source):
                raise ValueError("Invalid protected input range")
            previous = end
        events: dict[int, list[int]] = {0: [0, 0], len(layout.source): [0, 0]}
        syntax = (
            span
            for item in layout.ranges
            for span in (
                (item.outer_start, item.inner_start),
                (item.inner_end, item.outer_end),
            )
        )
        for channel, spans in enumerate((syntax, protected_spans)):
            for start, end in spans:
                events.setdefault(start, [0, 0])[channel] += 1
                events.setdefault(end, [0, 0])[channel] -= 1
        active = [0, 0]
        parts: list[InputPart] = []
        previous = 0
        for position, changes in sorted(events.items()):
            if previous < position:
                kind: Literal["text", "protected", "syntax"] = (
                    "syntax" if active[0] else "protected" if active[1] else "text"
                )
                if parts and parts[-1].kind == kind:
                    parts[-1] = InputPart(parts[-1].start, position, kind)
                else:
                    parts.append(InputPart(previous, position, kind))
            active = [value + change for value, change in zip(active, changes, strict=True)]
            previous = position
        return cls(layout, tuple(parts))

    @property
    def text(self) -> str:
        """Return wrapper-free text, including verbatim protected contents.

        This view alone loses protection metadata and must not be sent directly
        to a backend. In particular, code delimiters and excluded HTML may remain.
        """
        return "".join(
            self.layout.source[part.start : part.end]
            for part in self.parts
            if part.kind != "syntax"
        )
