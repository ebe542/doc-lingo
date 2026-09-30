"""Opt-in model input with markers for opaque content, not known wrappers."""

import re
from collections import Counter
from dataclasses import dataclass

from doc_lingo.documents.translation_input import TranslationInput
from doc_lingo.translation.issues import TranslationDiagnostics, retain_original
from doc_lingo.translation.markers import marker_prefix


@dataclass(frozen=True)
class ContentMarker:
    """A marker refers to original source content without copying it."""

    token: str
    start: int
    end: int


@dataclass(frozen=True)
class ModelInput:
    """Prepared text before token budgeting; never restores formatting itself.

    A None text means the complete source should bypass the model. Readers
    already omit standalone code blocks. This also handles wholly protected
    segments supplied directly by library callers.
    """

    source: TranslationInput
    text: str | None
    prefix: str
    markers: tuple[ContentMarker, ...]

    def restore_content(self, translated: str) -> str:
        """Restore exact contents, allowing marker movement with target grammar.

        On failure use the existing issue sink to retain the entire original;
        without a sink, the existing strict recovery policy raises instead.
        Successful output still needs formatting alignment before publication.
        """
        original = self.source.layout.source
        if self.text is None:
            return original
        pattern = re.compile(re.escape(self.prefix) + r"X[0-9]+Z")
        counts = Counter(pattern.findall(translated))
        replacements = {item.token: original[item.start : item.end] for item in self.markers}
        errors = [f"missing_marker: {key}" for key in replacements if counts[key] == 0]
        errors.extend(f"duplicate_marker: {key}" for key, count in counts.items() if count > 1)
        errors.extend(f"unexpected_marker: {key}" for key in counts if key not in replacements)
        if self.prefix.casefold() in pattern.sub("", translated).casefold():
            errors.append("damaged_marker")
        if not pattern.sub("", translated).strip():
            errors.append("empty_translated_text")
        if errors:
            return retain_original(
                original,
                "Content marker validation failed; source retained",
                diagnostics=TranslationDiagnostics(
                    translated, "protected", tuple(errors), replacements
                ),
            )
        return pattern.sub(lambda match: replacements[match[0]], translated)


def prepare_model_input(source: TranslationInput) -> ModelInput:
    """Remove known wrappers and mark opaque contents in source order.

    Whitespace needs no marker. Marker replacement adds no quotes, labels or
    extra padding, so existing source spacing is retained. Unknown adapter-owned
    syntax remains opaque until adapters provide more precise classification.
    """
    original = source.layout.source
    prefix = marker_prefix(original, namespace="DLM")
    if not any(
        part.kind == "text" and original[part.start : part.end].strip() for part in source.parts
    ):
        return ModelInput(source, None, prefix, ())
    pieces: list[str] = []
    markers: list[ContentMarker] = []
    for part in source.parts:
        content = original[part.start : part.end]
        if part.kind == "syntax":
            continue
        if part.kind == "protected" and content.strip():
            token = f"{prefix}X{len(markers)}Z"
            markers.append(ContentMarker(token, part.start, part.end))
            pieces.append(token)
        else:
            pieces.append(content)
    return ModelInput(source, "".join(pieces), prefix, tuple(markers))
