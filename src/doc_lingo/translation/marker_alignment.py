"""Replace statistical marker associations with validated exact identities."""

import re
from collections import Counter

from doc_lingo.translation.alignment import (
    AlignmentError,
    AlignmentLink,
    AlignmentResult,
    TextRange,
)
from doc_lingo.translation.model_input import ModelInput


def _subtract(span: TextRange, cuts: tuple[TextRange, ...]) -> list[TextRange]:
    result = []
    cursor = span.start
    for cut in cuts:
        if cut.end <= cursor or cut.start >= span.end:
            continue
        if cursor < cut.start:
            result.append(TextRange(cursor, cut.start))
        cursor = min(span.end, cut.end)
    if cursor < span.end:
        result.append(TextRange(cursor, span.end))
    return result


def anchor_content_markers(result: AlignmentResult, prepared: ModelInput) -> AlignmentResult:
    """Anchor only registered markers in a complete prepared segment.

    Reject invalid marker sets before modifying links. A statistical phrase that
    touches a marker is discarded as a whole: its other source ranges become
    ambiguous, since removing one edge cannot establish their true counterpart.
    Does not restore contents, run models, or claim linguistic placement is right.
    """
    if prepared.text is None or result.source != prepared.text:
        raise AlignmentError("Alignment source does not match prepared model input")
    tokens = tuple(item.token for item in prepared.markers)
    return anchor_registered_markers(result, tokens=tokens, prefix=prepared.prefix)


def anchor_registered_markers(
    result: AlignmentResult, *, tokens: tuple[str, ...], prefix: str
) -> AlignmentResult:
    """Anchor an explicitly supplied registry, never infer one from model output.

    This entry point also supports fixed evaluation pairs without fabricating a
    source document or ModelInput. Registry ownership remains with the caller.
    """
    if not prefix:
        raise AlignmentError("Marker namespace must not be empty")
    pattern = re.compile(re.escape(prefix) + r"X[0-9]+Z")
    if any(pattern.fullmatch(token) is None for token in tokens):
        raise AlignmentError("Registered marker does not match its namespace")
    if len(set(tokens)) != len(tokens):
        raise AlignmentError("Duplicate registered marker identity")
    positions = []
    for text in (result.source, result.target):
        matches = list(pattern.finditer(text))
        if Counter(m.group() for m in matches) != Counter(tokens):
            raise AlignmentError("Missing, duplicate or unexpected content marker")
        if prefix.casefold() in pattern.sub("", text).casefold():
            raise AlignmentError("Damaged content marker")
        positions.append({m.group(): TextRange(m.start(), m.end()) for m in matches})
    source_positions, target_positions = positions
    source_cuts = tuple(sorted(source_positions.values()))
    target_cuts = tuple(sorted(target_positions.values()))
    links = []
    ambiguous = [piece for span in result.ambiguous for piece in _subtract(span, source_cuts)]
    for link in result.links:
        touches = any(
            span.start < cut.end and span.end > cut.start
            for spans, cuts in (
                (link.source_ranges, source_cuts),
                (link.target_ranges, target_cuts),
            )
            for span in spans
            for cut in cuts
        )
        if touches:
            ambiguous.extend(
                piece for span in link.source_ranges for piece in _subtract(span, source_cuts)
            )
        else:
            links.append(link)
    links.extend(
        AlignmentLink((source_positions[token],), (target_positions[token],)) for token in tokens
    )
    return AlignmentResult(
        result.source,
        result.target,
        tuple(sorted(links, key=lambda link: link.source_ranges[0].start)),
        tuple(piece for span in result.unaligned for piece in _subtract(span, source_cuts)),
        tuple(sorted(ambiguous)),
    )
