"""Model-free Markdown review extraction; final reconstruction is not implemented."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from markdown_it import MarkdownIt
from markdown_it.rules_inline.state_inline import StateInline

from doc_lingo.documents.markdown._parser import _regions
from doc_lingo.documents.models import TextSegment
from doc_lingo.documents.source_layout import SourceRange
from doc_lingo.review.jobs import ReviewBlock, ReviewJob, ReviewJobError


@dataclass(frozen=True)
class MarkdownSource:
    """Offsets into the decoded snapshot; formatting offsets are block-local.

    Protected values are visible code or opaque reference labels, not markers.
    The source snapshot owns the exact delimiters and destinations.
    """

    start: int
    end: int
    formatting: tuple[SourceRange, ...]
    protected: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            type(self.start) is not int
            or type(self.end) is not int
            or not 0 <= self.start < self.end
        ):
            raise ReviewJobError("Invalid Markdown source positions")
        if not isinstance(self.formatting, tuple) or not all(
            isinstance(item, SourceRange)
            and all(
                type(v) is int
                for v in (item.outer_start, item.inner_start, item.inner_end, item.outer_end)
            )
            for item in self.formatting
        ):
            raise ReviewJobError("Invalid Markdown formatting evidence")
        if not isinstance(self.protected, tuple) or not all(
            isinstance(value, str) and value for value in self.protected
        ):
            raise ReviewJobError("Invalid protected Markdown contents")


def validate_protected(values: tuple[str, ...], text: str) -> None:
    """Reject missing, repeated or overlapping literal matches rather than guess."""
    occupied: list[tuple[int, int]] = []
    for value in values:
        left = r"(?<!\w)" if value[:1].isalnum() or value.startswith("_") else ""
        right = r"(?!\w)" if value[-1:].isalnum() or value.endswith("_") else ""
        matches = list(re.finditer(left + "(?=" + re.escape(value) + right + ")", text))
        if not value or len(matches) != 1:
            raise ReviewJobError("Protected content is missing or ambiguous")
        start = matches[0].start()
        end = start + len(value)
        if any(start < b and a < end for a, b in occupied):
            raise ReviewJobError("Protected content has ambiguous overlapping occurrences")
        occupied.append((start, end))


def _parser() -> MarkdownIt:
    parser = MarkdownIt("commonmark").enable(["table", "strikethrough"])
    # Keep implicit reference labels opaque, as the document adapter does.
    names = parser.get_active_rules()["inline"]
    rule = parser.inline.ruler.getRules("")[names.index("link")]

    def link(state: StateInline, silent: bool) -> bool:
        start, count = state.pos, len(state.tokens)
        if state.src[start : start + 1] != "[":
            return rule(state, silent)
        end = state.md.helpers.parseLinkLabel(state, start, True)
        matched = rule(state, silent)
        if matched and not silent and state.src[end + 1 : state.pos] in ("", "[]"):
            for token in state.tokens[count:]:
                if token.type == "link_open":
                    token.meta["review_protected"] = True
        return matched

    parser.inline.ruler.at("link", link)
    return parser


def markdown_blocks(data: bytes) -> tuple[ReviewBlock, ...]:
    """Extract supported prose using the document adapter's existing block IDs.

    Pure code, metadata and noneditable regions remain only in the snapshot.
    Mixed HTML/images fail explicitly until their review representation is defined.
    Unknown Markdown dialect syntax can still be ordinary text to CommonMark.
    """
    source = data.decode("utf-8-sig")
    parser = _parser()
    blocks = []
    for region in _regions(source):
        segment = region.segment
        if segment.type == "html_text":
            raise ReviewJobError(f"Block {segment.id}: HTML review is not supported yet")
        environment = getattr(segment, "environment", {})
        # Parse outer list/heading syntax away; table cells are already isolated.
        if segment.type == "table_cell":
            containers = parser.parseInline(segment.text, dict(environment))
        else:
            containers = parser.parse(segment.text, dict(environment))
        parts: list[str] = []
        protected: list[str] = []
        links: list[tuple[int, bool]] = []
        for container in containers:
            for token in container.children or ():
                if token.type == "text":
                    parts.append(token.content)
                elif token.type == "code_inline":
                    parts.append(token.content)
                    protected.append(token.content)
                elif token.type in ("softbreak", "hardbreak"):
                    parts.append("\n")
                elif token.type in ("html_inline", "image"):
                    raise ReviewJobError(
                        f"Block {segment.id}: inline HTML/image review is not supported yet"
                    )
                elif token.type == "link_open":
                    links.append(
                        (
                            len(parts),
                            bool(token.markup == "autolink" or token.meta.get("review_protected")),
                        )
                    )
                elif token.type == "link_close":
                    start, opaque = links.pop()
                    if opaque:
                        protected.append("".join(parts[start:]))
                elif token.type not in (
                    "em_open",
                    "em_close",
                    "strong_open",
                    "strong_close",
                    "s_open",
                    "s_close",
                ):
                    raise ReviewJobError(f"Block {segment.id}: unsupported inline token")
        text = "".join(parts)
        evidence = MarkdownSource(
            region.start, region.end, segment.source_layout().ranges, tuple(protected)
        )
        try:
            validate_protected(evidence.protected, text)
        except ReviewJobError as error:
            raise ReviewJobError(f"Block {segment.id}: {error}") from error
        blocks.append(ReviewBlock(segment.id, segment.type, text, text, evidence))
    return tuple(blocks)


def create_markdown_job(
    source: str | Path,
    proposals: Iterable[TextSegment],
    *,
    source_lang: str,
    target_lang: str,
) -> ReviewJob:
    """Accept ordered plain-text proposals, not translated Markdown or model markers.

    Use markdown_review_segments to obtain the input inventory. This API does not
    invoke a model and does not enable Markdown preparation/finalization in the CLI.
    """
    path = Path(source)
    data = path.read_bytes()
    values = iter(proposals)
    blocks = []
    for block in markdown_blocks(data):
        proposal = next(values, None)
        if not isinstance(proposal, TextSegment) or (proposal.id, proposal.type) != (
            block.id,
            block.type,
        ):
            raise ReviewJobError("Proposals must match source block IDs and types in order")
        blocks.append(
            ReviewBlock(block.id, block.type, block.original, proposal.text, block.source_info)
        )
    if next(values, None) is not None:
        raise ReviewJobError("Unexpected extra proposal")
    job = ReviewJob(
        str(uuid4()),
        path.name,
        source_lang,
        target_lang,
        sha256(data).hexdigest(),
        data,
        tuple(blocks),
        schema_version=2,
        document_format="md",
    )
    job.verify_source(path)
    return job


def markdown_review_segments(source: str | Path) -> tuple[TextSegment, ...]:
    """Return plain review blocks; these are not protection-aware model requests."""
    return tuple(
        TextSegment(b.id, b.original, b.type) for b in markdown_blocks(Path(source).read_bytes())
    )
