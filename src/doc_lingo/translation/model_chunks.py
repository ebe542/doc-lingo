"""Budget prepared input while retaining source and formatting relationships."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass

from doc_lingo.translation.chunks import split_text
from doc_lingo.translation.issues import issue_sink, retain_original
from doc_lingo.translation.model_input import ModelInput


@dataclass(frozen=True)
class ModelChunk:
    """One input unit and its separator, with source-local references.

    ``text=None`` means retain ``original`` without calling the model. Otherwise
    ``text`` satisfies the supplied tokenizer budget. ``original`` and source
    spans include the following separator; ``formatting`` indexes the shared
    SourceLayout ranges. These are source associations, not target alignment.
    """

    text: str | None
    separator: str
    original: str
    source_spans: tuple[tuple[int, int], ...]
    formatting: tuple[int, ...]


@dataclass(frozen=True)
class _Mapping:
    start: int
    end: int
    source_start: int
    source_end: int
    marker: bool


def _mapping(prepared: ModelInput) -> list[_Mapping]:
    """Derive temporary input offsets from the existing source partition."""
    markers = {(item.start, item.end): item.token for item in prepared.markers}
    position = 0
    result = []
    for part in prepared.source.parts:
        if part.kind == "syntax":
            continue
        marker = markers.get((part.start, part.end))
        length = len(marker) if marker is not None else part.end - part.start
        result.append(
            _Mapping(position, position + length, part.start, part.end, marker is not None)
        )
        position += length
    return result


def split_model_input(prepared: ModelInput, fits: Callable[[str], bool]) -> Iterator[ModelChunk]:
    """Keep fitting segments whole; split oversized input without cutting markers.

    ``fits`` must include the backend's actual tokenizer, special tokens and
    prompt overhead. No model calls are made here. As in existing recovery,
    oversized indivisible input is retained with an issue sink, or raises for
    strict callers. The active backend chunking path is not changed.
    """
    source = prepared.source.layout.source
    if prepared.text is None:
        yield ModelChunk(
            None,
            "",
            source,
            ((0, len(source)),) if source else (),
            tuple(range(len(prepared.source.layout.ranges))),
        )
        return
    mappings = _mapping(prepared)
    cursor = 0
    mapping_index = 0
    chunks = split_text(prepared.text, fits)
    try:
        while True:
            failures: list[str] = []
            # Capture only around next(), never while yielding to a caller.
            # split_text reports model input; report source content below instead.
            token = issue_sink.set(
                lambda original, reason, captured=failures: captured.append(reason)
            )
            try:
                try:
                    text, separator = next(chunks)
                except StopIteration:
                    return
            finally:
                issue_sink.reset(token)
            end = cursor + len(text) + len(separator)
            spans: list[tuple[int, int]] = []
            while mapping_index < len(mappings) and mappings[mapping_index].end <= cursor:
                mapping_index += 1
            index = mapping_index
            while index < len(mappings) and mappings[index].start < end:
                item = mappings[index]
                start_in_input, end_in_input = max(cursor, item.start), min(end, item.end)
                if item.marker:
                    # Current splitting uses whitespace; generated markers have
                    # none. Refuse partial markers if that contract ever changes.
                    if start_in_input != item.start or end_in_input != item.end:
                        raise ValueError("A model chunk splits a content marker")
                    span = (item.source_start, item.source_end)
                else:
                    span = (
                        item.source_start + start_in_input - item.start,
                        item.source_start + end_in_input - item.start,
                    )
                spans.append(span)
                index += 1
            original = "".join(source[a:b] for a, b in spans)
            formatting = tuple(
                index
                for index, item in enumerate(prepared.source.layout.ranges)
                if any(a < item.inner_end and b > item.inner_start for a, b in spans)
            )
            if failures:
                retain_original(original, failures[0])
                # split_text carries retained model text in its separator. Do
                # not expose that marker-bearing string as publishable spacing.
                separator = ""
            yield ModelChunk(text or None, separator, original, tuple(spans), formatting)
            cursor = end
    finally:
        chunks.close()
