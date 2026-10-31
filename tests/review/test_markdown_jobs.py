"""Markdown review evidence and plain-text correction contracts, without models."""

import json
from dataclasses import replace
from zipfile import ZipFile

import pytest

from doc_lingo.documents.models import TextSegment
from doc_lingo.review import (
    ReviewJobError,
    create_markdown_job,
    export_review_txt,
    finalize_text_review,
    import_review_txt,
    load_job,
    markdown_review_segments,
    save_job,
)


def make_job(tmp_path, text="Call `predict()` before **saving**.\n", proposal=None):
    source = tmp_path / "source.md"
    source.write_bytes(text.encode("utf-8"))
    segments = markdown_review_segments(source)
    if proposal is not None:
        segments = (TextSegment(segments[0].id, proposal, segments[0].type),)
    return create_markdown_job(source, segments, source_lang="en", target_lang="de")


def test_plain_blocks_snapshot_and_stored_evidence(tmp_path):
    source = (
        "\ufeff---\r\ntitle: Keep\r\n---\r\n\r\n# **Heading**\r\n\r\n"
        "- Call `predict()` before *saving*.\r\n\r\n"
        "> Read [the guide](https://example.org).\r\n\r\n"
        "| Name | Value |\r\n| --- | --- |\r\n| **Model** | One |\r\n\r\n"
        "```python\r\n# Keep comment\r\npass\r\n```\r\n\r\n<!-- Keep comment -->\r\n"
    )
    job = make_job(tmp_path, source)
    assert [b.original for b in job.blocks] == [
        "Heading",
        "Call predict() before saving.",
        "Read the guide.",
        "Name",
        "Value",
        "Model",
        "One",
    ]
    assert [b.type for b in job.blocks[:3]] == ["heading", "bullet_item", "blockquote"]
    assert job.source == source.encode("utf-8")
    block = job.blocks[1]
    assert block.source_info.protected == ("predict()",)
    raw = source.removeprefix("\ufeff")[block.source_info.start : block.source_info.end]
    assert raw == "- Call `predict()` before *saving*.\r\n"
    assert block.source_info.formatting
    assert job.schema_version == 2
    archive = tmp_path / "job.zip"
    save_job(job, archive)
    assert load_job(archive) == job
    with ZipFile(archive) as stored:
        assert sorted(stored.namelist()) == ["job.json", "source.md"]
    review = tmp_path / "review.txt"
    export_review_txt(job, review)
    content = review.read_text(encoding="utf-8")
    assert "Call predict() before saving." in content
    assert "`predict()`" not in content
    assert "Keep comment" not in content
    assert "https://example.org" not in content
    assert [s.text for s in import_review_txt(job, review)] == [b.proposal for b in job.blocks]


@pytest.mark.parametrize(
    "source, expected, protected",
    [
        ("Use ~~old~~ and **new**.", "Use old and new.", ()),
        ("Use `` a`b `` now.", "Use a`b now.", ("a`b",)),
        ("Line one  \nline two.", "Line one\nline two.", ()),
        (
            "See <https://example.org> now.",
            "See https://example.org now.",
            ("https://example.org",),
        ),
        ("Mail <a@example.org> now.", "Mail a@example.org now.", ("a@example.org",)),
        ("See [guide] now.\n\n[guide]: /help", "See guide now.", ("guide",)),
        ("See [guide][] now.\n\n[guide]: /help", "See guide now.", ("guide",)),
        ("See [guide][id] now.\n\n[id]: /help", "See guide now.", ()),
        ("Use &amp; and \\* literally.", "Use & and * literally.", ()),
    ],
)
def test_plain_projection(tmp_path, source, expected, protected):
    job = make_job(tmp_path, source)
    assert job.blocks[0].original == expected
    assert job.blocks[0].source_info.protected == protected


@pytest.mark.parametrize(
    "text",
    [
        "Use <b>bold</b> here.",
        "See ![picture](picture.png) here.",
        "<div>Hello</div>\n",
    ],
)
def test_unsupported_mixed_content_fails_explicitly(tmp_path, text):
    with pytest.raises(ReviewJobError, match="Block 1:.*not supported"):
        make_job(tmp_path, text)


@pytest.mark.parametrize("text", ["", "```py\n# Comment\n```\n", "`only_code`\n"])
def test_nonprose_stays_in_snapshot_without_review_blocks(tmp_path, text):
    job = make_job(tmp_path, text)
    assert job.blocks == ()
    assert job.source == text.encode()
    path = tmp_path / "empty.zip"
    save_job(job, path)
    assert load_job(path) == job


@pytest.mark.parametrize(
    "text",
    [
        "Call `model` then `model`.",
        "Use `model` and model.",
        "Call `foo()` then `foo`.",
    ],
)
def test_ambiguous_protected_content_is_rejected(tmp_path, text):
    with pytest.raises(ReviewJobError, match="Block 1:.*ambiguous"):
        make_job(tmp_path, text)


def test_correction_can_reorder_code_without_retranslation(tmp_path):
    job = make_job(tmp_path, "Call `predict()` before `save()`.")
    path = tmp_path / "review.txt"
    export_review_txt(job, path)
    content = path.read_text(encoding="utf-8").replace(
        "--- Correction ---\n\n", "--- Correction ---\nVor save() bitte predict() aufrufen.\n"
    )
    path.write_text(content, encoding="utf-8", newline="\n")
    assert import_review_txt(job, path)[0].text == "Vor save() bitte predict() aufrufen."


@pytest.mark.parametrize(
    "correction",
    [
        "Bitte aufrufen.",
        "Bitte predict() und predict() aufrufen.",
        "Bitte predict(1) aufrufen.",
    ],
)
def test_damaged_correction_is_rejected_with_block_id(tmp_path, correction):
    job = make_job(tmp_path)
    path = tmp_path / "review.txt"
    export_review_txt(job, path)
    content = path.read_text(encoding="utf-8").replace(
        "--- Correction ---\n\n", f"--- Correction ---\n{correction}\n"
    )
    path.write_text(content, encoding="utf-8", newline="\n")
    with pytest.raises(ReviewJobError, match="Block 1: Protected"):
        import_review_txt(job, path)


def test_modified_code_word_is_not_a_valid_match(tmp_path):
    with pytest.raises(ReviewJobError, match="Block 1: Protected"):
        make_job(tmp_path, "Keep `model` unchanged.", "Keep models unchanged.")


@pytest.mark.parametrize("kind", ["missing", "extra", "type", "empty", "changed_code"])
def test_invalid_proposals(tmp_path, kind):
    job = make_job(tmp_path)
    block = job.blocks[0]
    values = [TextSegment(block.id, block.proposal, block.type)]
    if kind == "missing":
        values.clear()
    elif kind == "extra":
        values *= 2
    elif kind == "type":
        values[0] = replace(values[0], type="heading")
    else:
        values[0] = replace(values[0], text=" " if kind == "empty" else "Changed")
    with pytest.raises(ReviewJobError):
        create_markdown_job(tmp_path / "source.md", values, source_lang="en", target_lang="de")


def test_source_changed_during_proposals(tmp_path):
    job = make_job(tmp_path)
    source = tmp_path / "source.md"

    def proposals():
        for block in job.blocks:
            yield TextSegment(block.id, block.proposal, block.type)
        source.write_bytes(b"changed")

    with pytest.raises(ReviewJobError, match="changed"):
        create_markdown_job(source, proposals(), source_lang="en", target_lang="de")


@pytest.mark.parametrize(
    "kind",
    [
        "position",
        "boolean",
        "formatting",
        "protected",
        "absent",
        "array",
        "member",
    ],
)
def test_tampered_archive_evidence_is_rejected(tmp_path, kind):
    job = make_job(tmp_path)
    path = tmp_path / "job.zip"
    save_job(job, path)
    with ZipFile(path) as archive:
        metadata = json.loads(archive.read("job.json"))
    info = metadata["blocks"][0]["source_info"]
    if kind == "position":
        info["end"] -= 1
    elif kind == "boolean":
        info["start"] = False
    elif kind == "formatting":
        info["formatting"] = []
    elif kind == "protected":
        info["protected"] = ["other"]
    elif kind == "array":
        info["protected"] = "predict()"
    elif kind == "absent":
        del metadata["blocks"][0]["source_info"]
    with ZipFile(path, "w") as archive:
        archive.writestr("job.json", json.dumps(metadata))
        archive.writestr("source.txt" if kind == "member" else "source.md", job.source)
    with pytest.raises(ReviewJobError):
        load_job(path)


def test_markdown_cannot_accidentally_use_txt_finalizer(tmp_path):
    job = make_job(tmp_path)
    output = tmp_path / "final.txt"
    with pytest.raises(ReviewJobError, match="requires a TXT"):
        finalize_text_review(job, tmp_path / "missing-review.txt", output)
    assert not output.exists()
    assert not list(tmp_path.glob(".doc-lingo-*"))
