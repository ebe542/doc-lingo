"""Reproducible writer validation for opt-in aligned Markdown output."""

import re
from dataclasses import dataclass, replace

from doc_lingo.documents.html.text import HtmlSegment
from doc_lingo.documents.markdown._parser import _MarkdownSegment
from doc_lingo.documents.markdown.rendering import render_markdown
from doc_lingo.documents.models import TextSegment
from doc_lingo.translation.formatting_bridge import RestoredFormatting


@dataclass(frozen=True)
class AlignedMarkdownSegment(TextSegment):
    restored: RestoredFormatting | None = None


def aligned_body(
    source: _MarkdownSegment | HtmlSegment,
) -> tuple[str, _MarkdownSegment | HtmlSegment, str]:
    """Keep adapter-owned block prefixes and outer whitespace outside models."""
    prefix = re.match(r"[ \t]*(?:(?:>[ \t]?|(?:[-+*]|\d+[.)])[ \t]+|#{1,6}[ \t]+))*", source.text)
    assert prefix is not None
    start = prefix.end()
    if isinstance(source, HtmlSegment):
        start = len(source.text) - len(source.text.lstrip())
    # Only remove syntax the reader has actually marked as protected.
    if start and not any(a == 0 and b >= start for a, b in source.protected_spans):
        start = 0
    end = max(start, len(source.text.rstrip()))
    body = replace(
        source,
        text=source.text[start:end],
        protected_spans=tuple(
            (max(a, start) - start, min(b, end) - start)
            for a, b in source.protected_spans
            if max(a, start) < min(b, end)
        ),
    )
    return source.text[:start], body, source.text[end:]


def aligned_errors(source: TextSegment, translated: AlignedMarkdownSegment) -> tuple[str, ...]:
    """Expose the same structural checks used by the writer for diagnostics."""
    if not isinstance(source, (_MarkdownSegment, HtmlSegment)) or translated.restored is None:
        return ("missing_alignment_evidence",)
    leading, body, trailing = aligned_body(source)
    layout = body.source_layout()
    baseline = replace(source, text=leading + layout.extract_text() + trailing, protected_spans=())
    target = leading + translated.restored.text + trailing
    errors = (
        baseline.validation_errors(target, allow_softbreaks=True)
        if isinstance(baseline, _MarkdownSegment)
        else baseline.validation_errors(target)
    )
    rendered = render_markdown(
        layout,
        translated.restored,
        environment=source.environment if isinstance(source, _MarkdownSegment) else {},
        raw_html=isinstance(source, HtmlSegment),
    ).text
    if leading + rendered + trailing != translated.text:
        errors += ("rendered_alignment_mismatch",)
    return errors


def accepts_aligned(source: TextSegment, translated: AlignedMarkdownSegment) -> bool:
    """Re-render evidence and retain all non-projected structural constraints."""
    return not aligned_errors(source, translated)
