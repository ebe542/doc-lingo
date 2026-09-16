"""Split source text without token decoding or losing source separators."""

import re
from collections.abc import Callable, Iterator

from doc_lingo.translation.issues import RecoverableTranslationError, retain_original

_BOUNDARY = re.compile(r"\s+")
_SENTENCE_END = re.compile(r"[.!?][\"'\u201d\u2019)]*$")


def split_text(text: str, fits: Callable[[str], bool]) -> Iterator[tuple[str, str]]:
    """Yield (text, following separator), preferring sentence to word boundaries.

    Sentence detection is a punctuation heuristic, not linguistic parsing.
    Balanced subdivision bounds recursion work; every yielded chunk is measured
    with the backend's actual tokenizer. No monotonic token-count assumption is
    made. An indivisible oversized word fails rather than corrupting its spelling.
    """
    pending = [(text, "")]
    while pending:
        part, separator = pending.pop()
        if fits(part):
            yield part, separator
            continue
        # Document readers retain final line endings. Keep outer whitespace
        # outside oversized model input rather than treating it as word content.
        core = part.strip()
        if core != part:
            leading = part[: len(part) - len(part.lstrip())]
            trailing = part[len(part.rstrip()) :]
            if not core:
                yield "", part + separator
                continue
            if leading:
                yield "", leading
            pending.append((core, trailing + separator))
            continue
        boundaries = [
            match
            for match in _BOUNDARY.finditer(part)
            if match.start() > 0 and match.end() < len(part)
        ]
        if not boundaries:
            original = retain_original(part, "A word exceeds the input token budget")
            yield "", original + separator
            continue
        sentences = [m for m in boundaries if _SENTENCE_END.search(part, 0, m.start())]

        def distance_from_middle(match: re.Match[str], midpoint: float = len(part) / 2) -> float:
            return abs(match.start() - midpoint)

        boundary = min(sentences or boundaries, key=distance_from_middle)
        pending.append((part[boundary.end() :], separator))
        pending.append((part[: boundary.start()], boundary.group()))


def translate_chunks(
    text: str, fits: Callable[[str], bool], translate: Callable[[str], str]
) -> str:
    """Return one segment only after all its chunks have translated successfully."""

    # Use individual sentences even when a whole paragraph fits the context.
    # Context capacity is not evidence that a model preserves long inputs.
    def sentences() -> Iterator[tuple[str, str]]:
        start = 0
        for boundary in _BOUNDARY.finditer(text):
            if _SENTENCE_END.search(text, start, boundary.start()):
                yield text[start : boundary.start()], boundary.group()
                start = boundary.end()
        if start < len(text):
            yield text[start:], ""

    def generate(part: str) -> str:
        if not part:
            return ""
        try:
            return translate(part)
        except RecoverableTranslationError as error:
            return retain_original(part, str(error))

    return "".join(
        "".join(generate(part) + separator for part, separator in split_text(sentence, fits))
        + following
        for sentence, following in sentences()
    )
