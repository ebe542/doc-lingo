"""Scoped reporting of recoverable translation failures without global state leaks."""

from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass

from doc_lingo.translation.protocols import TranslationError


class RecoverableTranslationError(TranslationError):
    """A single text unit failed; retaining its source is safe."""


@dataclass(frozen=True)
class TranslationDiagnostics:
    """Untrusted intermediate output, explicitly separated from original text."""

    attempted_translation: str | None
    stage: str
    validation_errors: tuple[str, ...]
    protected_fragments: dict[str, str] | None = None


@dataclass(frozen=True)
class TranslationIssue:
    original: str
    reason: str
    segment_id: str
    segment_type: str
    segment_number: int
    paragraph_number: int | None
    page: int | None = None
    action: str = "retained_original"
    diagnostics: TranslationDiagnostics | None = None


issue_sink: ContextVar[Callable[[str, str], None] | None] = ContextVar("issue_sink", default=None)
issue_details: ContextVar[TranslationDiagnostics | None] = ContextVar("issue_details", default=None)


def retain_original(
    text: str, reason: str, *, diagnostics: TranslationDiagnostics | None = None
) -> str:
    """Strict callers get an error; reporting callers retain the exact source."""
    sink = issue_sink.get()
    if sink is None:
        raise RecoverableTranslationError(reason)
    token = issue_details.set(diagnostics)
    try:
        sink(text, reason)
    finally:
        issue_details.reset(token)
    return text
