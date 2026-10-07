"""Format-independent alignment contracts; no alignment algorithm is selected."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, order=True)
class TextRange:
    """A nonempty half-open range of Python characters, not bytes or tokens."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if not 0 <= self.start < self.end:
            raise ValueError("Text range must be nonempty and nonnegative")


def _validate_ranges(ranges: tuple[TextRange, ...], limit: int | None = None) -> None:
    previous = 0
    for span in ranges:
        if span.start < previous:
            raise ValueError("Text ranges must be ordered and non-overlapping")
        if limit is not None and span.end > limit:
            raise ValueError("Text range exceeds the corresponding text length")
        previous = span.end


@dataclass(frozen=True)
class AlignmentLink:
    """One correspondence, including discontiguous many-to-many phrases.

    Ranges on each side are ordered locally. Links may reorder globally between
    languages. Shared words belong in one many-to-many link rather than repeated
    overlapping links. A link makes no claim of word-for-word correspondence.
    """

    source_ranges: tuple[TextRange, ...]
    target_ranges: tuple[TextRange, ...]

    def __post_init__(self) -> None:
        if not self.source_ranges or not self.target_ranges:
            raise ValueError("Alignment links require ranges on both sides")
        _validate_ranges(self.source_ranges)
        _validate_ranges(self.target_ranges)


@dataclass(frozen=True)
class TranslationUnit:
    """Exact source/target call boundaries, independent of word correspondences."""

    source: TextRange
    target: TextRange


@dataclass(frozen=True)
class AlignmentResult:
    """Alignment tied to the exact input/output strings of one model call.

    Every non-whitespace source character must be linked, unaligned, or
    ambiguous. Whitespace may be omitted. Unaligned means no counterpart was
    found; ambiguous means no unique assignment was selected. Neither permits
    automatic word-based formatting transfer. Separate translation-unit metadata
    can establish complete call boundaries without resolving individual words.
    Unlinked target text is allowed (insertions).
    Validation ensures structural consistency, not linguistic correctness.
    """

    source: str
    target: str
    links: tuple[AlignmentLink, ...] = ()
    unaligned: tuple[TextRange, ...] = ()
    ambiguous: tuple[TextRange, ...] = ()
    units: tuple[TranslationUnit, ...] = ()

    def __post_init__(self) -> None:
        _validate_ranges(tuple(unit.source for unit in self.units), len(self.source))
        _validate_ranges(tuple(unit.target for unit in self.units), len(self.target))
        _validate_ranges(self.unaligned, len(self.source))
        _validate_ranges(self.ambiguous, len(self.source))
        source_ranges = tuple(
            sorted(
                [span for link in self.links for span in link.source_ranges]
                + list(self.unaligned)
                + list(self.ambiguous)
            )
        )
        target_ranges = tuple(sorted(span for link in self.links for span in link.target_ranges))
        _validate_ranges(source_ranges, len(self.source))
        _validate_ranges(target_ranges, len(self.target))
        previous = 0
        for span in source_ranges:
            if self.source[previous : span.start].strip():
                raise ValueError("Non-whitespace source text has no alignment status")
            previous = span.end
        if self.source[previous:].strip():
            raise ValueError("Non-whitespace source text has no alignment status")


class AlignmentError(Exception):
    """An alignment implementation could not process a text pair."""


class TextAligner(Protocol):
    """Align exact model text before marker replacement or normalization.

    Implementations report expected operational failures as AlignmentError,
    without source text or credentials in error messages. Uncertain linguistic
    matches belong in the result, not in exceptions. This protocol does not
    prescribe dependencies, models, confidence scores or document syntax.
    """

    def align(self, source: str, target: str) -> AlignmentResult:
        """Return a result bound to these unchanged source and target strings."""
        ...


@runtime_checkable
class BudgetedTextAligner(TextAligner, Protocol):
    """Optional encoder-budget capability, measured without model inference."""

    def fits_input(self, text: str) -> bool:
        """Include tokenization and special tokens; never truncate input."""
        ...


@runtime_checkable
class ReservedTextAligner(BudgetedTextAligner, Protocol):
    """Optional smaller source budget leaves headroom for target expansion."""

    def fits_source(self, text: str) -> bool: ...
