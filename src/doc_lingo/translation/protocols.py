"""Provider-independent translation contract and expected errors."""

from typing import Protocol


class TranslationError(Exception):
    """A translation backend could not translate the requested text."""


class TranslationBackend(Protocol):
    """Translate text without knowledge of document paths or segment IDs.

    Implementations validate supported languages and map expected provider or
    model failures to TranslationError. Error messages must not contain source
    text or credentials. Unexpected programming errors should propagate intact.
    """

    def translate(self, text: str, *, source_lang: str, target_lang: str) -> str:
        """Return translated text or raise TranslationError for expected failures."""
        ...
