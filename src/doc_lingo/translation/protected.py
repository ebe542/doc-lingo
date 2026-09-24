"""Translate a complete segment while retaining adapter-owned syntax."""

import re
from uuid import uuid4

from doc_lingo.documents.models import TextSegment
from doc_lingo.translation.issues import (
    RecoverableTranslationError,
    issue_sink,
    retain_original,
)
from doc_lingo.translation.protocols import TranslationBackend


def translate_segment(
    segment: TextSegment, backend: TranslationBackend, *, source_lang: str, target_lang: str
) -> str:
    """Validate exact marker order; nested recovery retains the whole source unit."""
    if not segment.protected_spans:
        return backend.translate(segment.text, source_lang=source_lang, target_lang=target_lang)
    spans = list(segment.protected_spans)
    leading = ""
    trailing = ""
    cursor = 0
    limit = len(segment.text)
    if spans[0][0] == 0:
        _, cursor = spans.pop(0)
        leading = segment.text[:cursor]
    if spans and spans[-1][1] == limit:
        limit, _ = spans.pop()
        trailing = segment.text[limit:]
    if not spans:
        body = segment.text[cursor:limit]
        if not body.strip():
            return segment.text
        return (
            leading
            + backend.translate(body, source_lang=source_lang, target_lang=target_lang)
            + trailing
        )
    prefix = "DLM" + uuid4().hex.upper()
    while prefix in segment.text:
        prefix = "DLM" + uuid4().hex.upper()
    pieces = []
    replacements = {}
    padding = {}
    for start, end in spans:
        marker = f"{prefix}X{len(replacements)}Z"
        replacements[marker] = segment.text[start:end]
        left = not segment.text[start - 1].isspace()
        right = not segment.text[end].isspace()
        padding[marker] = (left, right)
        # Keep model/glossary word boundaries around opaque markers. Remove
        # injected spacing on restoration so emphasis stays attached to text.
        pieces.extend(
            (segment.text[cursor:start], " " if left else "", marker, " " if right else "")
        )
        cursor = end
    pieces.append(segment.text[cursor:limit])
    failed = False

    def record_failure(original: str, reason: str) -> None:
        nonlocal failed
        failed = True

    token = issue_sink.set(record_failure)
    try:
        try:
            translated = backend.translate(
                "".join(pieces), source_lang=source_lang, target_lang=target_lang
            )
        except RecoverableTranslationError:
            failed = True
            translated = ""
    finally:
        issue_sink.reset(token)
    pattern = re.compile(re.escape(prefix) + r"X[0-9]+Z")
    if (
        failed
        or pattern.findall(translated) != list(replacements)
        or prefix in pattern.sub("", translated)
        or not pattern.sub("", translated).strip()
    ):
        return retain_original(segment.text, "Document syntax protection failed; source retained")
    padded = re.compile(r"([ \t]*)(" + pattern.pattern + r")([ \t]*)")

    def restore(match: re.Match[str]) -> str:
        marker = match[2]
        left, right = padding[marker]
        return ("" if left else match[1]) + replacements[marker] + ("" if right else match[3])

    return leading + padded.sub(restore, translated) + trailing
