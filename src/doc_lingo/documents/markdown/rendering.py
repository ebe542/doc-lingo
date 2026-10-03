"""Opt-in rendering of projected Markdown wrappers in restored target text."""

import re
from dataclasses import dataclass

from doc_lingo.documents.html.text import HtmlText
from doc_lingo.documents.markdown.layout import inline_source_layout
from doc_lingo.documents.source_layout import SourceLayout, SourceRange
from doc_lingo.translation.alignment import TextRange
from doc_lingo.translation.formatting import FormattingIssue, FormattingScope
from doc_lingo.translation.formatting_bridge import RestoredFormatting


@dataclass(frozen=True)
class MarkdownRendering:
    text: str
    issues: tuple[FormattingIssue, ...]


def html_wrapper(opening: str, closing: str) -> str | None:
    """Recognize complete inline wrappers; attributes stay byte-for-byte source-owned."""
    match = re.match(r"<([A-Za-z][A-Za-z0-9]*)\b", opening)
    if match is None or match[1].lower() not in {
        "strong",
        "em",
        "b",
        "i",
        "span",
        "a",
        "s",
        "u",
        "mark",
        "small",
        "sub",
        "sup",
    }:
        return None
    tag = match[1].lower()
    if not re.fullmatch(r"</" + tag + r"\s*>", closing, re.IGNORECASE):
        return None
    return tag


def markdown_scopes(layout: SourceLayout) -> tuple[FormattingScope, ...]:
    """Name every layout range by index; preserve link suffixes verbatim.

    Reference labels, destinations and optional titles remain source-owned.
    Unsupported wrappers are diagnosed by the renderer, not silently inferred.
    Empty content cannot become an alignment scope and is omitted.
    """
    return tuple(
        FormattingScope(
            str(index),
            TextRange(item.inner_start, item.inner_end),
            layout.source[item.inner_end : item.outer_end]
            if layout.source[item.outer_start : item.inner_start] == "["
            else layout.source[item.outer_start : item.inner_start]
            if html_wrapper(
                layout.source[item.outer_start : item.inner_start],
                layout.source[item.inner_end : item.outer_end],
            )
            == "a"
            else None,
        )
        for index, item in enumerate(layout.ranges)
        if item.inner_start < item.inner_end
    )


def render_markdown(
    layout: SourceLayout,
    restored: RestoredFormatting,
    *,
    environment: dict | None = None,
    raw_html: bool = False,
) -> MarkdownRendering:
    """Render nested/disjoint wrappers, dropping crossing or invalid scopes.

    Target offsets refer to restored.text, never to the growing Markdown output.
    Existing protected content stays verbatim. Parser validation checks that all
    inserted wrappers are recognized at their intended positions. If delimiter
    interactions defeat that check, discard the inserted formatting and retain
    restored text. This function does not activate the document writer or CLI.
    """
    scopes = {scope.identity: scope for scope in markdown_scopes(layout)}
    issues = list(restored.projection.issues)
    entries = []
    for item in restored.projection.formatting:
        identity = item.scope.identity
        if scopes.get(identity) != item.scope:
            raise ValueError("Projected scope does not match the Markdown source layout")
        source_range = layout.ranges[int(identity)]
        opening = layout.source[source_range.outer_start : source_range.inner_start]
        closing = layout.source[source_range.inner_end : source_range.outer_end]
        supported = (
            html_wrapper(opening, closing) is not None
            or (opening == closing and opening in ("*", "**", "_", "__", "~~"))
            or (opening == "[" and closing.startswith(("](", "][")))
        )
        if not supported:
            issues.append(FormattingIssue(identity, "dropped", "unsupported_markdown_wrapper"))
            continue
        previous = 0
        for span in item.target_ranges:
            if span.start < previous or span.end > len(restored.text):
                raise ValueError("Invalid Markdown target ranges")
            previous = span.end
            entries.append((span, int(identity), opening, closing))

    conflicts = set()
    for i, (left, left_id, _, _) in enumerate(entries):
        for right, right_id, _, _ in entries[i + 1 :]:
            crossing = (
                left.start < right.start < left.end < right.end
                or right.start < left.start < right.end < left.end
            )
            nested_links = (
                scopes[str(left_id)].link_target is not None
                and scopes[str(right_id)].link_target is not None
                and left.start < right.end
                and right.start < left.end
            )
            if crossing or nested_links:
                conflicts.update((left_id, right_id))
    for identity in sorted(conflicts):
        issues.append(FormattingIssue(str(identity), "dropped", "conflicting_markdown_ranges"))
    entries = [entry for entry in entries if entry[1] not in conflicts]
    # Open parents first and close children first, also for equal target ranges.
    events = {}
    for number, (span, identity, opening, closing) in enumerate(entries):
        events.setdefault(span.start, []).append((1, -span.end, identity, number, opening))
        events.setdefault(span.end, []).append((0, -span.start, -identity, number, closing))
    pieces = []
    position = 0
    length = 0
    starts = {}
    expected = []
    for offset in sorted(events):
        plain = restored.text[position:offset]
        pieces.append(plain)
        length += len(plain)
        for opening, _, _, number, wrapper in sorted(events[offset]):
            if opening:
                starts[number] = (length, length + len(wrapper))
            else:
                outer, inner = starts[number]
                expected.append(SourceRange(outer, inner, length, length + len(wrapper)))
            pieces.append(wrapper)
            length += len(wrapper)
        position = offset
    pieces.append(restored.text[position:])
    text = "".join(pieces)
    actual = (
        HtmlText(text).source_layout()
        if raw_html
        else inline_source_layout(text, environment or {}, HtmlText(text))
    )
    if not set(expected).issubset(actual.ranges):
        issues.extend(
            FormattingIssue(str(identity), "dropped", "markdown_wrapper_validation")
            for identity in sorted({entry[1] for entry in entries})
        )
        text = restored.text
    dropped = {issue.identity for issue in issues if issue.action == "dropped"}
    issues = [
        issue for issue in issues if issue.action == "dropped" or issue.identity not in dropped
    ]
    return MarkdownRendering(text, tuple(issues))
