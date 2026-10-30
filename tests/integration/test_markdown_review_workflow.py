"""Run the reusable Markdown review examples without models or manual steps."""

import json
import re
from pathlib import Path

import pytest

from doc_lingo import TextSegment
from doc_lingo.review import (
    ReviewJobError,
    create_markdown_job,
    export_review_txt,
    import_review_txt,
    load_job,
    markdown_review_segments,
    save_job,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "review"


@pytest.fixture
def review_example(tmp_path):
    source = tmp_path / "source.md"
    snapshot = (FIXTURES / "markdown-review.en.md").read_bytes()
    source.write_bytes(snapshot)
    cases = json.loads((FIXTURES / "markdown-review.en-de.json").read_text(encoding="utf-8"))
    segments = markdown_review_segments(source)
    assert len(segments) == 8
    assert [segment.text for segment in segments] == [case["original"] for case in cases]
    proposals = [
        TextSegment(segment.id, case["proposal"], segment.type)
        for segment, case in zip(segments, cases, strict=True)
    ]
    job = create_markdown_job(source, proposals, source_lang="en", target_lang="de")
    archive = tmp_path / "job.zip"
    save_job(job, archive)
    loaded = load_job(archive)
    assert loaded == job
    assert loaded.source == snapshot
    review = tmp_path / "review.txt"
    export_review_txt(loaded, review)
    yield loaded, cases, review
    assert source.read_bytes() == snapshot
    assert load_job(archive) == job


def corrected_text(review, cases):
    corrections = iter(case["correction"] for case in cases)
    text, count = re.subn(
        r"--- Correction ---\n\n",
        lambda match: "--- Correction ---\n" + next(corrections) + "\n",
        review.read_text(encoding="utf-8"),
    )
    assert count == len(cases)
    return text


def test_fixture_export_and_unchanged_import(review_example):
    job, cases, review = review_example
    data = review.read_bytes()
    assert b"\r" not in data
    text = data.decode("utf-8")
    for excluded in (
        "# Model prediction",
        "**saving**",
        "`predict()`",
        "*starting*",
        "https://example.org/guide",
        "```",
        "This comment",
        "Metadata stays",
    ):
        assert excluded not in text
    for case in cases:
        assert case["original"] in text
        assert case["proposal"] in text
    selected = import_review_txt(job, review)
    assert [segment.text for segment in selected] == [case["proposal"] for case in cases]
    assert [(segment.id, segment.type) for segment in selected] == [
        (block.id, block.type) for block in job.blocks
    ]


def test_fixture_corrections_and_empty_fallback(review_example, tmp_path):
    job, cases, review = review_example
    changed = tmp_path / "review_changed.txt"
    changed.write_text(corrected_text(review, cases), encoding="utf-8", newline="\n")
    selected = import_review_txt(job, changed)
    assert [segment.text for segment in selected] == [
        case["correction"] or case["proposal"] for case in cases
    ]
    assert selected[1].text == "Vor dem Speichern mit save() rufen Sie predict() auf."
    assert [segment.id for segment in selected] == [block.id for block in job.blocks]
    assert [segment.text for segment in import_review_txt(job, review)] == [
        case["proposal"] for case in cases
    ]


def test_fixture_damaged_code_reports_block_two(review_example, tmp_path):
    job, cases, review = review_example
    corrected = corrected_text(review, cases)
    original = cases[1]["correction"]
    assert corrected.count(original) == 1
    broken = corrected.replace(original, original.replace("predict()", "predict(1)"))
    invalid = tmp_path / "review_invalid.txt"
    invalid.write_text(broken, encoding="utf-8", newline="\n")
    with pytest.raises(ReviewJobError, match=r"Block 2: Protected content is missing"):
        import_review_txt(job, invalid)
    assert invalid.read_text(encoding="utf-8") == broken


@pytest.mark.parametrize(
    "name, reason",
    [
        ("markdown-ambiguous-code.en.md", r"Block 1:.*ambiguous"),
        ("markdown-inline-html.en.md", r"Block 1:.*HTML/image review is not supported"),
    ],
)
def test_unsupported_source_fixtures(name, reason):
    with pytest.raises(ReviewJobError, match=reason):
        markdown_review_segments(FIXTURES / name)
