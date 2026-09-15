"""Format-independent document data."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TextSegment:
    """Text with an opaque ID, unique and repeatable within an unchanged document."""

    id: str
    text: str
    type: str = "paragraph"
