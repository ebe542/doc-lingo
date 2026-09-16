"""Scoped reporting of recoverable translation failures without global state leaks."""

from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass

from doc_lingo.translation.protocols import TranslationError


class RecoverableTranslationError(TranslationError):
    """A single text unit failed; retaining its source is safe."""


@dataclass(frozen=True)
class TranslationIssue:
    original: str
    reason: str
    segment_id: str
    segment_type: str
    segment_number: int
    paragraph_number: int | None
    page: int | None = None


issue_sink: ContextVar[Callable[[str, str], None] | None] = ContextVar("issue_sink", default=None)


def retain_original(text: str, reason: str) -> str:
    """Strict callers get an error; reporting callers retain the exact source."""
    sink = issue_sink.get()
    if sink is None:
        raise RecoverableTranslationError(reason)
    sink(text, reason)
    return text
