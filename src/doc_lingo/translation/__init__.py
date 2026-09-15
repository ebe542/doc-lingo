"""Translation contracts and application service."""

from doc_lingo.translation.protocols import TranslationBackend, TranslationError
from doc_lingo.translation.service import translate_document

__all__ = ["TranslationBackend", "TranslationError", "translate_document"]
