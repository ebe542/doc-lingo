"""Versioned, immutable review data with an exact source snapshot."""

from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO, TextIOWrapper
from pathlib import Path
from uuid import UUID, uuid4

from doc_lingo.documents.models import TextSegment
from doc_lingo.documents.plain_text.blocks import iter_text_blocks


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
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ReviewJobError("Unsupported review job version")
        if self.document_format != "txt":
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
            expected = source_segments(self.source)
        except UnicodeError:
            raise ReviewJobError("Review source is not UTF-8 TXT") from None
        if not isinstance(self.blocks, tuple) or len(expected) != len(self.blocks):
            raise ReviewJobError("Review block inventory does not match source")
        for original, block in zip(expected, self.blocks, strict=True):
            if not isinstance(block, ReviewBlock) or (block.id, block.type, block.original) != (
                original.id,
                original.type,
                original.text,
            ):
                raise ReviewJobError("Review block identity, order or original text mismatch")
            if not isinstance(block.proposal, str) or not block.proposal.strip():
                raise ReviewJobError(
                    "Review proposal must contain text; retain original on failure"
                )

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
