"""Experimental UTF-8 review interchange, independent of document formatting."""

import json
import os
import re
from pathlib import Path
from tempfile import TemporaryDirectory

from doc_lingo.documents.models import TextSegment
from doc_lingo.review.jobs import ReviewJob, ReviewJobError

_HEADER = "doc-lingo-review: 1"
_ORIGINAL = "--- Original ---"
_TRANSLATION = "--- Translation ---"
_CORRECTION = "--- Correction ---"
_END = "=== End Block ==="
_BLOCK = re.compile(r"=== Block ([A-Za-z0-9._:-]+) ===")
MAX_REVIEW_BYTES = 128 * 1024 * 1024


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _reserved(line: str) -> bool:
    return line in {_HEADER, _ORIGINAL, _TRANSLATION, _CORRECTION, _END} or bool(
        _BLOCK.fullmatch(line)
    )


def _encode(text: str) -> str:
    return "\n".join(
        "\\" + line if line.startswith("\\") or _reserved(line) else line
        for line in _normalize(text).split("\n")
    )


def _source_label(name: str) -> str:
    # JSON string escaping without quotes keeps ordinary filenames readable.
    return "Source: " + json.dumps(name, ensure_ascii=False)[1:-1]


def export_review_txt(job: ReviewJob, destination: str | Path) -> None:
    """Publish a new text review; the job and existing output files stay untouched."""
    job.validate()
    destination = Path(destination)
    if os.path.lexists(destination):
        raise FileExistsError(f"Review document already exists: {destination}")
    parts = [_HEADER + "\n", f"Job-ID: {job.id}\n\n"]
    for block in job.blocks:
        parts.extend(
            (
                f"=== Block {block.id} ===\n",
                _source_label(job.source_name) + "\n",
                _ORIGINAL + "\n",
                _encode(block.original) + "\n",
                _TRANSLATION + "\n",
                _encode(block.proposal) + "\n",
                _CORRECTION + "\n\n",
                _END + "\n\n",
            )
        )
    data = "".join(parts).encode("utf-8")
    if len(data) > MAX_REVIEW_BYTES:
        raise ReviewJobError("Text review exceeds size limit")
    with TemporaryDirectory(prefix=".doc-lingo-review-", dir=destination.parent) as directory:
        temporary = Path(directory) / "review.txt"
        temporary.write_bytes(data)
        os.link(temporary, destination)


class _Parser:
    def __init__(self, text: str):
        self.lines = text.split("\n")
        self.position = 0

    def take(self) -> str:
        if self.position >= len(self.lines):
            raise ReviewJobError("Unexpected end of text review")
        line = self.lines[self.position]
        self.position += 1
        return line

    def expect(self, expected: str) -> None:
        if self.take() != expected:
            raise ReviewJobError(f"Expected review control or reference: {expected}")

    def section(self, terminator: str) -> str:
        lines = []
        while True:
            line = self.take()
            if line == terminator:
                if not lines:
                    raise ReviewJobError("Review section is missing its framing newline")
                return "\n".join(lines)
            if line.startswith("\\"):
                literal = line[1:]
                if not (literal.startswith("\\") or _reserved(literal)):
                    raise ReviewJobError(
                        "Invalid text review escape; double a literal leading backslash"
                    )
                line = literal
            elif _reserved(line):
                raise ReviewJobError("Unexpected review control; escape literal control lines")
            lines.append(line)


def import_review_txt(job: ReviewJob, source: str | Path) -> tuple[TextSegment, ...]:
    """Validate a complete review and select text in original job order.

    BOM and editor newline conventions are accepted. Reference sections are
    immutable; payload whitespace is preserved except for newline normalization.
    """
    job.validate()
    with Path(source).open("rb") as stream:
        data = stream.read(MAX_REVIEW_BYTES + 1)
    if len(data) > MAX_REVIEW_BYTES:
        raise ReviewJobError("Text review exceeds size limit")
    try:
        text = _normalize(data.decode("utf-8-sig"))
    except UnicodeError:
        raise ReviewJobError("Text review must use UTF-8") from None
    parser = _Parser(text)
    parser.expect(_HEADER)
    parser.expect(f"Job-ID: {job.id}")
    parser.expect("")
    expected = {block.id: block for block in job.blocks}
    selected = {}
    while parser.position < len(parser.lines):
        line = parser.take()
        if line == "":
            continue
        match = _BLOCK.fullmatch(line)
        if match is None:
            raise ReviewJobError("Unexpected text outside review blocks")
        identity = match[1]
        if identity not in expected or identity in selected:
            raise ReviewJobError(f"Unknown or duplicate review block ID: {identity}")
        block = expected[identity]
        try:
            parser.expect(_source_label(job.source_name))
            parser.expect(_ORIGINAL)
            original = parser.section(_TRANSLATION)
            proposal = parser.section(_CORRECTION)
            correction = parser.section(_END)
            if original != _normalize(block.original) or proposal != _normalize(block.proposal):
                raise ReviewJobError("Reference text changed; move edits into Correction")
            selected[identity] = correction if correction.strip() else block.proposal
            if block.source_info is not None:
                from doc_lingo.review.markdown import validate_protected

                validate_protected(block.source_info.protected, selected[identity])
        except ReviewJobError as error:
            raise ReviewJobError(f"Block {identity}: {error}") from error
    if selected.keys() != expected.keys():
        raise ReviewJobError("Text review contains missing blocks")
    return tuple(TextSegment(b.id, selected[b.id], b.type) for b in job.blocks)
