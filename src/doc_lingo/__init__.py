"""Document translation with formatting preservation."""

from doc_lingo.documents import DocumentReader, DocumentWriter, SegmentMismatchError, TextSegment
from doc_lingo.huggingface import HuggingFaceBackend
from doc_lingo.plain_text import PlainTextReader
from doc_lingo.plain_text_writer import PlainTextWriter
from doc_lingo.translation import TranslationBackend, TranslationError, translate_document

__all__ = [
    "DocumentReader",
    "DocumentWriter",
    "HuggingFaceBackend",
    "PlainTextReader",
    "PlainTextWriter",
    "SegmentMismatchError",
    "TextSegment",
    "TranslationBackend",
    "TranslationError",
    "translate_document",
]
