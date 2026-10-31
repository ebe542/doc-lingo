"""Fixed TXT examples exercise persistence through final document publication."""

import json
import re
from pathlib import Path

import pytest

from doc_lingo import PlainTextReader, TextSegment
from doc_lingo.review import (
    create_text_job,
    export_review_txt,
    finalize_text_review,
    import_review_txt,
    load_job,
    save_job,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "review"


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("bom", [b"", b"\xef\xbb\xbf"])
@pytest.mark.parametrize("corrected", [False, True], ids=["proposals", "corrections"])
def test_fixture_complete_txt_review_workflow(tmp_path, newline, bom, corrected):
    cases = json.loads((FIXTURES / "text-review.en-de.json").read_text(encoding="utf-8"))
    source = tmp_path / "source.txt"
    original = (FIXTURES / "text-review.en.txt").read_text(encoding="utf-8")
    source_bytes = bom + original.replace("\n", newline).encode("utf-8")
    source.write_bytes(source_bytes)
    with PlainTextReader(source).iter_segments() as values:
        segments = tuple(values)
    assert [(s.type, s.text.replace("\r\n", "\n")) for s in segments] == [
        (case["type"], case["original"]) for case in cases
    ]
    proposals = [
        TextSegment(s.id, case["proposal"].replace("\n", newline), s.type)
        for s, case in zip(segments, cases, strict=True)
    ]
    job = create_text_job(source, proposals, source_lang="en", target_lang="de")
    archive = tmp_path / "job.zip"
    save_job(job, archive)
    archive_bytes = archive.read_bytes()
    loaded = load_job(archive)
    assert loaded == job
    assert loaded.source == source_bytes
    review = tmp_path / "review.txt"
    export_review_txt(loaded, review)
    exported = review.read_bytes()
    assert b"\r" not in exported
    text = exported.decode("utf-8")
    assert "- Read the guide." not in text
    assert "1. Keep the original data." not in text
    assert "Keep **literal** text." in text
    reviewed = tmp_path / "review_returned.txt"
    if corrected:
        corrections = iter(case["correction"] for case in cases)
        text, count = re.subn(
            r"--- Correction ---\n\n",
            lambda match: "--- Correction ---\n" + next(corrections) + "\n",
            text,
        )
        assert count == len(cases)
        # A translator may return blocks in another order; IDs own placement.
        header, *blocks = re.split(r"(?=^=== Block \d+ ===$)", text, flags=re.MULTILINE)
        text = header + "".join(reversed(blocks))
    reviewed.write_bytes(b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))
    returned_bytes = reviewed.read_bytes()
    selected = import_review_txt(loaded, reviewed)
    assert [(s.id, s.type) for s in selected] == [(s.id, s.type) for s in segments]
    assert [s.text for s in selected] == [
        case["correction"] if corrected and case["correction"] else proposal.text
        for case, proposal in zip(cases, proposals, strict=True)
    ]
    output = tmp_path / "final.de.txt"
    finalize_text_review(loaded, reviewed, output, original=source)
    expected_name = "text-review.corrected.de.txt" if corrected else "text-review.proposed.de.txt"
    expected = (FIXTURES / expected_name).read_text(encoding="utf-8")
    assert output.read_bytes() == bom + expected.replace("\n", newline).encode("utf-8")
    assert source.read_bytes() == source_bytes
    assert archive.read_bytes() == archive_bytes
    assert review.read_bytes() == exported
    assert reviewed.read_bytes() == returned_bytes
    assert not list(tmp_path.glob(".doc-lingo-*"))
