"""Document contracts and format adapters."""

from doc_lingo.documents.errors import SegmentMismatchError
from doc_lingo.documents.models import TextSegment
from doc_lingo.documents.protocols import DocumentReader, DocumentWriter
from doc_lingo.documents.source_layout import SourceLayout, SourceRange

__all__ = [
    "DocumentReader",
    "DocumentWriter",
    "SegmentMismatchError",
    "SourceLayout",
    "SourceRange",
    "TextSegment",
]
