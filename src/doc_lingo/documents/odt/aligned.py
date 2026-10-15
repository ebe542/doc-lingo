"""Render projected ODT wrappers with source-owned XML and opaque contents."""

import re
from dataclasses import dataclass, replace
from xml.parsers import expat
from xml.sax.saxutils import escape

from doc_lingo.documents.models import TextSegment
from doc_lingo.documents.odt.inline import OdtInlineSegment
from doc_lingo.documents.odt.package import OdtPackageError
from doc_lingo.documents.source_layout import SourceRange
from doc_lingo.translation.alignment import TextRange
from doc_lingo.translation.formatting import FormattingIssue, FormattingScope
from doc_lingo.translation.formatting_bridge import RestoredFormatting


@dataclass(frozen=True)
class AlignedOdtSegment(TextSegment):
    """Rendered inner XML plus reproducible projection evidence for the writer."""

    restored: RestoredFormatting | None = None


def aligned_body(source: OdtInlineSegment) -> tuple[str, OdtInlineSegment]:
    """Keep only unwrapped leading frames at their original paragraph boundary.

    Interior frames, bookmarks, fields and explicit whitespace retain markers.
    A frame enclosed by a style/link is not independent of that scope.
    """
    end = 0
    for left, right in source.frame_spans:
        if source.text[end:left].strip() or any(r.outer_start < right for r in source.ranges):
            break
        end = right
    if not end:
        return "", source
    return source.text[:end], replace(
        source,
        text=source.text[end:],
        protected_spans=tuple((a - end, b - end) for a, b in source.protected_spans if a >= end),
        ranges=tuple(
            SourceRange(
                r.outer_start - end, r.inner_start - end, r.inner_end - end, r.outer_end - end
            )
            for r in source.ranges
        ),
        frame_spans=tuple((a - end, b - end) for a, b in source.frame_spans if a >= end),
    )


def render_segment(source: OdtInlineSegment, restored: RestoredFormatting):
    """Reconstruct the same source-owned prefix in the service and writer."""
    prefix, body = aligned_body(source)
    rendered, issues = render_aligned(body, restored)
    return prefix + rendered, issues


def supports_projection(source: OdtInlineSegment) -> bool:
    """Do not move namespace declarations or duplicate unique XML identities."""
    return not any(
        re.search(
            r"\s(?:xmlns(?::[^\s=]+)?|xml:id)\s*=", source.text[r.outer_start : r.inner_start]
        )
        for r in source.ranges
    )


def odt_scopes(source: OdtInlineSegment) -> tuple[FormattingScope, ...]:
    return tuple(
        FormattingScope(
            str(index),
            TextRange(r.inner_start, r.inner_end),
            source.text[r.outer_start : r.inner_start]
            if re.match(r"<(?:[^\s:>]+:)?a(?:\s|>)", source.text[r.outer_start : r.inner_start])
            else None,
        )
        for index, r in enumerate(source.ranges)
        if r.inner_start < r.inner_end and index not in source.language_ranges
    )


def render_aligned(
    source: OdtInlineSegment, restored: RestoredFormatting
) -> tuple[str, tuple[FormattingIssue, ...]]:
    """Escape prose, retain opaque XML exactly and insert only source wrappers.

    Crossing styles and overlapping links are discarded. Opaque elements retain
    their order, including paired bookmarks; no projected boundary may cut them.
    The writer repeats rendering instead of trusting supplied XML text.
    """
    if not supports_projection(source):
        raise OdtPackageError("Unsupported ODT projection scope")
    text = restored.text
    fragments = [
        source.text[p.start : p.end]
        for p in source.translation_input().parts
        if p.kind == "protected"
    ]
    opaque = []
    visible = []
    cursor = 0
    for fragment in fragments:
        position = text.find(fragment, cursor)
        if position < 0 or any(item in text[cursor:position] for item in fragments):
            raise OdtPackageError("ODT aligned protection changed")
        visible.append(text[cursor:position])
        opaque.append((position, position + len(fragment)))
        cursor = position + len(fragment)
    if any(item in text[cursor:] for item in fragments):
        raise OdtPackageError("ODT aligned protection changed")
    visible.append(text[cursor:])
    if not "".join(visible).strip():
        raise OdtPackageError("Empty aligned ODT text")
    scopes = {item.identity: item for item in odt_scopes(source)}
    issues = list(restored.projection.issues)
    entries = []
    seen = set()
    for item in restored.projection.formatting:
        if scopes.get(item.scope.identity) != item.scope or item.scope.identity in seen:
            raise OdtPackageError("ODT projection scope does not match source")
        seen.add(item.scope.identity)
        previous = 0
        for span in item.target_ranges:
            if span.start < previous or span.end > len(text):
                raise OdtPackageError("Invalid ODT projection range")
            previous = span.end
            if any(a < boundary < b for a, b in opaque for boundary in (span.start, span.end)):
                raise OdtPackageError("ODT projection splits protected content")
            entries.append((span, int(item.scope.identity)))
    conflicts = set()
    for i, (left, left_id) in enumerate(entries):
        for right, right_id in entries[i + 1 :]:
            crossing = (
                left.start < right.start < left.end < right.end
                or right.start < left.start < right.end < left.end
            )
            links = (
                scopes[str(left_id)].link_target is not None
                and scopes[str(right_id)].link_target is not None
                and left.start < right.end
                and right.start < left.end
            )
            if crossing or links:
                conflicts.update((left_id, right_id))
    issues.extend(
        FormattingIssue(str(i), "dropped", "conflicting_odt_ranges") for i in sorted(conflicts)
    )
    issues.extend(
        FormattingIssue(str(i), "dropped", "no_visible_content")
        for i, r in enumerate(source.ranges)
        if r.inner_start == r.inner_end and i not in source.language_ranges
    )
    events = {}
    for span, identity in entries:
        if identity in conflicts:
            continue
        r = source.ranges[identity]
        events.setdefault(span.start, []).append(
            (1, -span.end, identity, source.text[r.outer_start : r.inner_start])
        )
        events.setdefault(span.end, []).append(
            (0, -span.start, -identity, source.text[r.inner_end : r.outer_end])
        )
    boundaries = sorted({0, len(text), *events, *(p for pair in opaque for p in pair)})
    pieces = []
    protected = set(opaque)
    for index, position in enumerate(boundaries):
        pieces.extend(event[3] for event in sorted(events.get(position, ())))
        if index + 1 < len(boundaries):
            end = boundaries[index + 1]
            part = text[position:end]
            pieces.append(part if (position, end) in protected else escape(part))
    rendered = "".join(pieces)
    try:
        # Namespace bindings belong to the unchanged package ancestors. This
        # local check validates nesting and XML characters without resolving them.
        expat.ParserCreate().Parse("<root>" + rendered + "</root>", True)
    except (expat.ExpatError, UnicodeError):
        raise OdtPackageError("Invalid aligned ODT XML") from None
    dropped = {i.identity for i in issues if i.action == "dropped"}
    return rendered, tuple(i for i in issues if i.action == "dropped" or i.identity not in dropped)
