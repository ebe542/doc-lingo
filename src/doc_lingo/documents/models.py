"""Format-independent document data."""

from dataclasses import dataclass, field

from doc_lingo.documents.source_layout import SourceLayout


@dataclass(frozen=True)
class TextSegment:
    """Text with an opaque ID, unique and repeatable within an unchanged document."""

    id: str
    text: str
    type: str = "paragraph"
    protected_spans: tuple[tuple[int, int], ...] = ()
    unrepaired_text: str | None = field(default=None, kw_only=True)

    def __post_init__(self) -> None:
        """Protected ranges use ordered, non-overlapping Python string offsets."""
        previous = 0
        for start, end in self.protected_spans:
            if not previous <= start < end <= len(self.text):
                raise ValueError("Invalid protected text range")
            previous = end

    def source_layout(self) -> SourceLayout:
        """Return source-local inline wrappers for opt-in extraction."""
        return SourceLayout(self.text)

    def accepts_translation(self, text: str) -> bool:
        """Adapters may reject translations that would change document structure."""
        return True

    def repair_translation(self, text: str) -> str | None:
        """Return a narrowly validated formatting repair, or None if unsupported."""
        return None

    def validation_errors(self, text: str) -> tuple[str, ...]:
        """Explain an adapter rejection without changing its validation policy."""
        return () if self.accepts_translation(text) else ("document_structure_changed",)
