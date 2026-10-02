"""Translation contracts and application service."""

from doc_lingo.translation.alignment import (
    AlignmentError,
    AlignmentLink,
    AlignmentResult,
    TextAligner,
    TextRange,
)
from doc_lingo.translation.formatting import (
    FormattingIssue,
    FormattingProjection,
    FormattingScope,
    ProjectedFormatting,
    project_formatting,
)
from doc_lingo.translation.formatting_bridge import RestoredFormatting, restore_aligned_formatting
from doc_lingo.translation.protocols import TranslationBackend, TranslationError
from doc_lingo.translation.service import translate_document

__all__ = [
    "RestoredFormatting",
    "restore_aligned_formatting",
    "FormattingScope",
    "FormattingIssue",
    "FormattingProjection",
    "ProjectedFormatting",
    "project_formatting",
    "AlignmentError",
    "AlignmentLink",
    "AlignmentResult",
    "TextAligner",
    "TextRange",
    "TranslationBackend",
    "TranslationError",
    "translate_document",
]
