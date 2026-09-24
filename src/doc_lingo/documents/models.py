"""Format-independent document data."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TextSegment:
    """Text with an opaque ID, unique and repeatable within an unchanged document."""

    id: str
    text: str
    type: str = "paragraph"
    protected_spans: tuple[tuple[int, int], ...] = ()

    def __post_init__(self) -> None:
        """Protected ranges use ordered, non-overlapping Python string offsets."""
        previous = 0
        for start, end in self.protected_spans:
            if not previous <= start < end <= len(self.text):
                raise ValueError("Invalid protected text range")
            previous = end

    def accepts_translation(self, text: str) -> bool:
        """Adapters may reject translations that would change document structure."""
        return True
