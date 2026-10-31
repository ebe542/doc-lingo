"""Reconstruct Markdown from reviewed plain text, never translating corrections."""

import os
import re
import string
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory

from doc_lingo.documents.markdown._parser import _regions
from doc_lingo.documents.markdown.rendering import markdown_scopes, render_markdown
from doc_lingo.documents.models import TextSegment
from doc_lingo.review.jobs import ReviewJob, ReviewJobError
from doc_lingo.review.markdown import _parser, locate_protected, markdown_blocks
from doc_lingo.review.text import import_review_txt
from doc_lingo.translation.alignment import AlignmentError, AlignmentResult, TextAligner, TextRange
from doc_lingo.translation.formatting import (
    FormattingIssue,
    FormattingProjection,
    ProjectedFormatting,
    project_formatting,
)
from doc_lingo.translation.formatting_bridge import RestoredFormatting
from doc_lingo.translation.issues import TranslationDiagnostics, TranslationIssue


@dataclass(frozen=True)
class _PlainLayout:
    text: str
    content: str
    scopes: tuple[TextRange, ...]
    protected: tuple[tuple[str, str], ...]
    hard_breaks: bool


def _plain_layout(segment: TextSegment) -> _PlainLayout:
    """Read visible token offsets while retaining original protected spelling."""
    parser = _parser()
    environment = dict(getattr(segment, "environment", {}))
    containers = (
        parser.parseInline(segment.text, environment)
        if segment.type == "table_cell"
        else parser.parse(segment.text, environment)
    )
    inline = [token for token in containers if token.type == "inline"]
    if len(inline) != 1:
        raise ReviewJobError("Cannot identify a single Markdown inline container")
    parts = []
    length = 0
    scopes: list[TextRange | None] = []
    stack = []
    protected = []
    opaque = None
    for token in inline[0].children or ():
        if token.type in ("text", "code_inline", "softbreak", "hardbreak"):
            text = "\n" if token.type in ("softbreak", "hardbreak") else token.content
            parts.append(text)
            length += len(text)
            if token.type == "code_inline" and opaque is None:
                protected.append((text, token.meta["review_raw"]))
        elif opaque is not None:
            if token.type == "link_close":
                start, raw = opaque
                protected.append(("".join(parts)[start:length], raw))
                opaque = None
        elif token.nesting == 1:
            if token.type == "link_open" and (
                token.markup == "autolink" or token.meta.get("review_protected")
            ):
                opaque = (length, token.meta["review_raw"])
            else:
                stack.append((len(scopes), length))
                scopes.append(None)
        elif token.nesting == -1:
            index, start = stack.pop()
            if start == length:
                raise ReviewJobError("Empty formatting scope cannot be reconstructed")
            scopes[index] = TextRange(start, length)
    if stack or opaque is not None or any(scope is None for scope in scopes):
        raise ReviewJobError("Unbalanced Markdown review formatting")
    return _PlainLayout(
        "".join(parts),
        inline[0].content,
        tuple(scope for scope in scopes if scope is not None),
        tuple(protected),
        any(token.type == "hardbreak" for token in inline[0].children or ()),
    )


def _escape_and_restore(target: str, protected: tuple[tuple[str, str], ...]):
    """Map plain offsets to escaped Markdown; protected interiors are indivisible."""
    spans = locate_protected(tuple(value for value, _ in protected), target)
    replacements = {
        start: (end, raw) for (start, end), (_, raw) in zip(spans, protected, strict=True)
    }
    offsets: dict[int, int] = {0: 0}
    pieces = []
    position = length = 0
    while position < len(target):
        offsets[position] = length
        if position in replacements:
            end, piece = replacements[position]
        else:
            char = target[position]
            piece = "\\" + char if char in string.punctuation else char
            end = position + 1
        pieces.append(piece)
        length += len(piece)
        position = end
        offsets[position] = length
    return "".join(pieces), offsets


def _wrap_block(segment: TextSegment, content: str, rendered: str) -> str:
    """Retain outer syntax and use container prefixes for new physical lines."""
    if segment.type == "table_cell":
        if "\n" in rendered or "\r" in rendered:
            raise ReviewJobError("A table cell correction must stay on one line")
        return rendered
    lines = segment.text.splitlines(keepends=True)
    contents = content.split("\n")
    prefixes = []
    endings = []
    starts = []
    ends = []
    cursor = 0
    for index, part in enumerate(contents):
        if index >= len(lines):
            raise ReviewJobError("Cannot recover Markdown line boundaries")
        line = lines[index]
        bare = line.rstrip("\r\n")
        suffix = r"[ \t]*(?:#+[ \t]*)?" if segment.type == "heading" else r"[ \t]*"
        matches = [
            m for m in re.finditer(re.escape(part), bare) if re.fullmatch(suffix, bare[m.end() :])
        ]
        if not matches:
            raise ReviewJobError("Cannot recover Markdown content boundaries")
        match = matches[0]
        prefixes.append(bare[: match.start()])
        endings.append(line[len(bare) :])
        starts.append(cursor + match.start())
        ends.append(cursor + match.end())
        cursor += len(line)
    target_lines = rendered.split("\n")
    continuation = (
        prefixes[-1]
        if len(prefixes) > 1
        else re.sub(r"(?:[-+*]|\d+[.)])[ \t]+", lambda m: " " * len(m[0]), prefixes[0])
    )
    pieces = [segment.text[: starts[0]], target_lines[0]]
    newline = next((ending for ending in endings if ending), "\n")
    for index, line in enumerate(target_lines[1:], 1):
        prefix = prefixes[index] if index < len(prefixes) else continuation
        pieces.extend((newline, prefix, line))
    pieces.append(segment.text[ends[-1] :])
    return "".join(pieces)


def _render_block(segment, block, target, aligner):
    plain = _plain_layout(segment)
    if plain.text != block.original:
        raise ReviewJobError("Plain-text source mapping changed")
    layout = segment.source_layout()
    original_scopes = markdown_scopes(layout)
    if len(original_scopes) != len(plain.scopes):
        raise ReviewJobError("Formatting scope inventory changed")
    scopes = tuple(
        replace(scope, source=span)
        for scope, span in zip(original_scopes, plain.scopes, strict=True)
    )
    if target == plain.text:
        return segment.text, ()
    alignment = AlignmentResult(plain.text, target, unaligned=(TextRange(0, len(plain.text)),))
    if scopes and aligner is not None:
        try:
            alignment = aligner.align(plain.text, target)
            if alignment.source != plain.text or alignment.target != target:
                raise AlignmentError("Alignment text does not match reviewed text")
        except AlignmentError:
            # Text remains authoritative; unresolved scopes are reported below.
            alignment = AlignmentResult(
                plain.text, target, unaligned=(TextRange(0, len(plain.text)),)
            )
    projection = project_formatting(alignment, scopes, complete_segment=True)
    escaped, offsets = _escape_and_restore(target, plain.protected)
    mapped = []
    issues = list(projection.issues)
    if plain.hard_breaks:
        issues.append(FormattingIssue("line_breaks", "dropped", "hard_line_breaks_not_projected"))
    for item in projection.formatting:
        if any(r.start not in offsets or r.end not in offsets for r in item.target_ranges):
            issues.append(
                FormattingIssue(item.scope.identity, "dropped", "partial_protected_content")
            )
            continue
        mapped.append(
            ProjectedFormatting(
                original_scopes[int(item.scope.identity)],
                tuple(TextRange(offsets[r.start], offsets[r.end]) for r in item.target_ranges),
            )
        )
    rendered = render_markdown(
        layout,
        RestoredFormatting(escaped, FormattingProjection(tuple(mapped), tuple(issues))),
        environment=getattr(segment, "environment", {}),
    )
    return _wrap_block(segment, plain.content, rendered.text), rendered.issues


def _block_structure(text: str) -> list[tuple]:
    """Ignore inline styles but retain block hierarchy and excluded code contents."""
    parser = _parser()
    return [
        (
            t.type,
            t.tag,
            t.nesting,
            t.markup,
            t.attrs,
            t.content if t.type in ("fence", "code_block", "html_block") else None,
        )
        for t in parser.parse(text)
        if t.type != "inline"
    ]


def finalize_markdown_review(
    job: ReviewJob,
    review: str | Path,
    destination: str | Path,
    *,
    original: str | Path | None = None,
    aligner: TextAligner | None = None,
    on_issue: Callable[[TranslationIssue], None] | None = None,
) -> tuple[TranslationIssue, ...]:
    """Publish a new Markdown document from reviewed text and return all warnings.

    Optional alignment transfers partial formatting; no translator is called.
    Callback failures prevent publication. Snapshot source and input files stay
    untouched. Uncertain formatting is omitted, never the reviewed text.
    """
    job.validate()
    if job.document_format != "md":
        raise ReviewJobError("Markdown finalization requires a Markdown review job")
    destination = Path(destination)
    if os.path.lexists(destination):
        raise FileExistsError(f"Output file already exists: {destination}")
    if original is not None:
        job.verify_source(original)
    selected = import_review_txt(job, review)
    source = job.source.decode("utf-8-sig")
    regions = tuple(_regions(source))
    pieces = []
    issues = []
    cursor = 0
    for number, (region, block, target) in enumerate(
        zip(regions, job.blocks, selected, strict=True), 1
    ):
        try:
            rendered, warnings = _render_block(region.segment, block, target.text, aligner)
        except ReviewJobError as error:
            raise ReviewJobError(f"Block {block.id}: {error}") from error
        pieces.extend((source[cursor : region.start], rendered))
        cursor = region.end
        issues.extend(
            TranslationIssue(
                block.original,
                "Formatting projection: " + warning.reason,
                block.id,
                block.type,
                number,
                None,
                action="formatting_" + warning.action,
                diagnostics=TranslationDiagnostics(
                    target.text, "review_finalization", (warning.diagnostic(),)
                ),
            )
            for warning in warnings
        )
    pieces.append(source[cursor:])
    text = "".join(pieces)
    data = (b"\xef\xbb\xbf" if job.source.startswith(b"\xef\xbb\xbf") else b"") + text.encode(
        "utf-8"
    )
    reconstructed = markdown_blocks(data)
    if [(b.id, b.type, b.original) for b in reconstructed] != [
        (s.id, s.type, s.text) for s in selected
    ]:
        raise ReviewJobError("Reviewed text changes Markdown block structure or visible contents")
    if _block_structure(text) != _block_structure(source):
        raise ReviewJobError("Reviewed text changes Markdown block structure")
    if on_issue is not None:
        for issue in issues:
            on_issue(issue)
    with TemporaryDirectory(prefix=".doc-lingo-review-", dir=destination.parent) as directory:
        temporary = Path(directory) / "final.md"
        temporary.write_bytes(data)
        os.link(temporary, destination)
    return tuple(issues)
