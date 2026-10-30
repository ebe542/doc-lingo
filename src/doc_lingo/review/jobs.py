"""Versioned, immutable review data with an exact source snapshot."""

from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO, TextIOWrapper
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from doc_lingo.documents.models import TextSegment
from doc_lingo.documents.plain_text.blocks import iter_text_blocks

if TYPE_CHECKING:
    from doc_lingo.review.markdown import MarkdownSource


class ReviewJobError(ValueError):
    """A job is inconsistent, unsupported or no longer matches its source."""


def source_segments(data: bytes) -> tuple[TextSegment, ...]:
    """Reuse TXT block boundaries, preserving BOM and newlines in the snapshot."""
    with TextIOWrapper(BytesIO(data), encoding="utf-8-sig", newline="") as stream:
        segments = []
        for block in iter_text_blocks(stream):
            if block.text is not None:
                segments.append(TextSegment(str(len(segments) + 1), block.text, block.type))
        return tuple(segments)


@dataclass(frozen=True)
class ReviewBlock:
    id: str
    type: str
    original: str
    proposal: str
    source_info: "MarkdownSource | None" = None


@dataclass(frozen=True)
class ReviewJob:
    id: str
    source_name: str
    source_lang: str
    target_lang: str
    source_sha256: str
    source: bytes
    blocks: tuple[ReviewBlock, ...]
    schema_version: int = 1
    document_format: str = "txt"

    def validate(self) -> None:
        if type(self.schema_version) is not int or self.schema_version not in (1, 2):
            raise ReviewJobError("Unsupported review job version")
        if (self.schema_version, self.document_format) not in ((1, "txt"), (2, "md")):
            raise ReviewJobError("Unsupported review document format")
        if not all(
            isinstance(v, str) and v.strip()
            for v in (
                self.id,
                self.source_name,
                self.source_lang,
                self.target_lang,
                self.source_sha256,
            )
        ):
            raise ReviewJobError("Missing or invalid review metadata")
        try:
            if str(UUID(self.id)) != self.id:
                raise ValueError
        except ValueError:
            raise ReviewJobError("Invalid review job identity") from None
        if "/" in self.source_name or "\\" in self.source_name or self.source_name in (".", ".."):
            raise ReviewJobError("Source name must be a filename")
        if (
            not isinstance(self.source, bytes)
            or sha256(self.source).hexdigest() != self.source_sha256
        ):
            raise ReviewJobError("Review source fingerprint mismatch")
        try:
            if self.document_format == "md":
                from doc_lingo.review.markdown import markdown_blocks

                expected_blocks = markdown_blocks(self.source)
            else:
                expected_blocks = tuple(
                    ReviewBlock(s.id, s.type, s.text, s.text) for s in source_segments(self.source)
                )
        except UnicodeError:
            raise ReviewJobError("Review source is not UTF-8") from None
        if not isinstance(self.blocks, tuple) or len(expected_blocks) != len(self.blocks):
            raise ReviewJobError("Review block inventory does not match source")
        for original, block in zip(expected_blocks, self.blocks, strict=True):
            if not isinstance(block, ReviewBlock) or (block.id, block.type, block.original) != (
                original.id,
                original.type,
                original.original,
            ):
                raise ReviewJobError("Review block identity, order or original text mismatch")
            if block.source_info != original.source_info:
                raise ReviewJobError(f"Block {block.id}: source evidence mismatch")
            if not isinstance(block.proposal, str) or not block.proposal.strip():
                raise ReviewJobError(
                    "Review proposal must contain text; retain original on failure"
                )
            if block.source_info is not None:
                from doc_lingo.review.markdown import validate_protected

                try:
                    validate_protected(block.source_info.protected, block.proposal)
                except ReviewJobError as error:
                    raise ReviewJobError(f"Block {block.id}: {error}") from error

    def verify_source(self, path: str | Path) -> None:
        """Check a caller-selected original; never resolve stored names as paths."""
        self.validate()
        if sha256(Path(path).read_bytes()).hexdigest() != self.source_sha256:
            raise ReviewJobError("Original document changed since job creation")


def create_text_job(
    source: str | Path,
    proposals: Iterable[TextSegment],
    *,
    source_lang: str,
    target_lang: str,
) -> ReviewJob:
    """Snapshot TXT and accept exactly one ordered proposal per source block.

    This function does not translate. Callers must retain original text in a
    proposal if translation failed, and keep the source stable during generation.
    """
    path = Path(source)
    data = path.read_bytes()
    values = iter(proposals)
    blocks = []
    for original in source_segments(data):
        proposal = next(values, None)
        if not isinstance(proposal, TextSegment) or (proposal.id, proposal.type) != (
            original.id,
            original.type,
        ):
            raise ReviewJobError("Proposals must match source block IDs and types in order")
        blocks.append(ReviewBlock(original.id, original.type, original.text, proposal.text))
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
    )
    job.verify_source(path)
    return job
