"""Document translation with formatting preservation."""

from doc_lingo.documents import DocumentReader, DocumentWriter, SegmentMismatchError, TextSegment
from doc_lingo.documents.plain_text import PlainTextReader
from doc_lingo.documents.plain_text_writer import PlainTextWriter
from doc_lingo.translation import TranslationBackend, TranslationError, translate_document
from doc_lingo.translation.huggingface import HuggingFaceBackend
from doc_lingo.translation.marian import MarianBackend

__all__ = [
    "DocumentReader",
    "DocumentWriter",
    "HuggingFaceBackend",
    "MarianBackend",
    "PlainTextReader",
    "PlainTextWriter",
    "SegmentMismatchError",
    "TextSegment",
    "TranslationBackend",
    "TranslationError",
    "translate_document",
]
