"""Document translation with formatting preservation."""

from doc_lingo.documents import DocumentReader, DocumentWriter, SegmentMismatchError, TextSegment
from doc_lingo.plain_text import PlainTextReader
from doc_lingo.plain_text_writer import PlainTextWriter

__all__ = [
    "DocumentReader",
    "DocumentWriter",
    "PlainTextReader",
    "PlainTextWriter",
    "SegmentMismatchError",
    "TextSegment",
]
