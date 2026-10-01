"""Translation contracts and application service."""

from doc_lingo.translation.alignment import (
    AlignmentError,
    AlignmentLink,
    AlignmentResult,
    TextAligner,
    TextRange,
)
from doc_lingo.translation.protocols import TranslationBackend, TranslationError
from doc_lingo.translation.service import translate_document

__all__ = [
    "AlignmentError",
    "AlignmentLink",
    "AlignmentResult",
    "TextAligner",
    "TextRange",
    "TranslationBackend",
    "TranslationError",
    "translate_document",
]
