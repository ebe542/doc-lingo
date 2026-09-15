"""Document contracts and format adapters."""

from doc_lingo.documents.errors import SegmentMismatchError
from doc_lingo.documents.models import TextSegment
from doc_lingo.documents.protocols import DocumentReader, DocumentWriter

__all__ = ["DocumentReader", "DocumentWriter", "SegmentMismatchError", "TextSegment"]
