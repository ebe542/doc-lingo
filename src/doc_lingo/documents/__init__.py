"""Document contracts and format adapters."""

from doc_lingo.documents.errors import SegmentMismatchError
from doc_lingo.documents.models import TextSegment
from doc_lingo.documents.protocols import DocumentReader, DocumentWriter
from doc_lingo.documents.source_layout import SourceLayout, SourceRange
from doc_lingo.documents.translation_input import InputPart, TranslationInput

__all__ = [
    "DocumentReader",
    "DocumentWriter",
    "InputPart",
    "SegmentMismatchError",
    "SourceLayout",
    "SourceRange",
    "TextSegment",
    "TranslationInput",
]
