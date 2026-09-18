"""Optional, format-independent terminology with validated placeholder restoration."""

import gzip
import json
import re
import zlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from doc_lingo.translation.issues import issue_sink, retain_original
from doc_lingo.translation.protocols import TranslationBackend, TranslationError
from doc_lingo.translation.term_matcher import TermMatcher, character_key


@dataclass(frozen=True)
class GlossaryEntry:
    source: str
    mode: str
    target: str = ""


@dataclass(frozen=True)
class Glossary:
    source_lang: str
    target_lang: str
    entries: tuple[GlossaryEntry, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_lang, str)
            or not self.source_lang.strip()
            or not isinstance(self.target_lang, str)
            or not self.target_lang.strip()
            or not self.entries
        ):
            raise ValueError("Glossary requires languages and entries")
        seen = set()
        for entry in self.entries:
            if not isinstance(entry, GlossaryEntry) or not all(
                isinstance(value, str) for value in (entry.source, entry.mode, entry.target)
            ):
                raise ValueError("Glossary entry values must be strings")
            if (
                not entry.source.strip()
                or entry.source != entry.source.strip()
                or "\n" in entry.source
                or "\r" in entry.source
                or tuple(map(character_key, entry.source)) in seen
                or entry.mode not in ("keep", "translate", "annotate")
                or (entry.mode != "keep" and not entry.target.strip())
                or (entry.mode == "keep" and entry.target)
                or "\n" in entry.target
                or "\r" in entry.target
            ):
                raise ValueError("Invalid or duplicate glossary entry")
            seen.add(tuple(map(character_key, entry.source)))

    @classmethod
    def load(cls, path: Path) -> "Glossary":
        """Load an explicit schema; malformed files fail before translation."""
        try:
            if path.name.lower().endswith(".json.gz"):
                with gzip.open(path, "rt", encoding="utf-8") as stream:
                    data = json.load(stream)
            else:
                data = json.loads(path.read_text(encoding="utf-8"))
            if type(data["schema_version"]) is not int or data["schema_version"] != 1:
                raise ValueError("Unsupported glossary schema")
            if not all(isinstance(data[k], str) for k in ("source_lang", "target_lang")):
                raise ValueError("Invalid glossary languages")
            if not isinstance(data["entries"], list):
                raise ValueError("Glossary entries must be an array")
            entries = tuple(GlossaryEntry(**item) for item in data["entries"])
            return cls(data["source_lang"], data["target_lang"], entries)
        except (KeyError, TypeError, AttributeError, EOFError, zlib.error) as error:
            raise ValueError("Invalid glossary schema") from error


class GlossaryBackend:
    """Wrap any translator; never trust the model to preserve placeholders.

    Matching is case-insensitive with Unicode word boundaries, longest term first.
    A recovery inside protected text invalidates the entire segment: source text
    is retained and reported instead of leaking placeholders or masked diagnostics.
    """

    def __init__(self, backend: TranslationBackend, glossary: Glossary) -> None:
        self.backend = backend
        self.glossary = glossary
        self._matcher = TermMatcher(entry.source for entry in glossary.entries)

    def translate(self, text: str, *, source_lang: str, target_lang: str) -> str:
        if (source_lang, target_lang) != (self.glossary.source_lang, self.glossary.target_lang):
            raise TranslationError("Glossary languages do not match the translation request")
        matches = list(self._matcher.finditer(text))
        if not matches:
            return self.backend.translate(text, source_lang=source_lang, target_lang=target_lang)
        if len(matches) == 1:
            start, end, index = matches[0]
            if not text[:start].strip() and not text[end:].strip():
                # A complete terminology entry needs no inference. Keep the
                # document's outer whitespace and the usual capitalization rule.
                entry = self.glossary.entries[index]
                original = text[start:end]
                replacement = original if entry.mode == "keep" else entry.target
                if entry.mode == "annotate":
                    replacement += f" ({original})"
                if entry.mode != "keep" and replacement[:1].islower():
                    replacement = replacement[0].upper() + replacement[1:]
                return text[:start] + replacement + text[end:]
        prefix = "DLG" + uuid4().hex.upper()
        while prefix in text:
            prefix = "DLG" + uuid4().hex.upper()
        replacements = {}

        pieces = []
        cursor = 0
        for start, end, index in matches:
            entry = self.glossary.entries[index]
            original = text[start:end]
            replacement = original if entry.mode == "keep" else entry.target
            if entry.mode == "annotate":
                replacement += f" ({original})"
            marker = f"{prefix}X{len(replacements)}Z"
            replacements[marker] = (replacement, entry.mode != "keep")
            pieces.extend((text[cursor:start], marker))
            cursor = end
        pieces.append(text[cursor:])
        masked = "".join(pieces)
        failed = False

        def record_failure(original: str, reason: str) -> None:
            nonlocal failed
            failed = True

        token = issue_sink.set(record_failure)
        try:
            translated = self.backend.translate(
                masked, source_lang=source_lang, target_lang=target_lang
            )
        finally:
            issue_sink.reset(token)
        markers = re.compile(re.escape(prefix) + r"X[0-9]+Z")
        if failed or Counter(markers.findall(translated)) != Counter(replacements.keys()):
            return retain_original(text, "Glossary protection failed; original segment retained")
        restored = markers.sub("", translated)
        if prefix in restored:
            return retain_original(text, "Unexpected glossary marker; original segment retained")

        # One substitution pass prevents glossary replacements from cascading.
        def restore(match: re.Match[str]) -> str:
            replacement, capitalize = replacements[match.group()]
            # Use the output position: a model can reorder source terms. Skip
            # surrounding quotes, but not a soft line break inside a sentence.
            position = match.start() - 1
            while position >= 0 and translated[position] in " \t\r\n\"'“”‘’«»„(":
                position -= 1
            sentence_start = position < 0 or translated[position] in ".!?"
            if capitalize and sentence_start and replacement[:1].islower():
                replacement = replacement[0].upper() + replacement[1:]
            return replacement

        return markers.sub(restore, translated)
