"""Persistent jobs preserve source evidence independently of model dependencies."""

import json
from dataclasses import replace
from zipfile import ZipFile

import pytest

from doc_lingo import PlainTextReader, TextSegment
from doc_lingo.review import ReviewJobError, create_text_job, load_job, save_job


def make_job(tmp_path):
    source = tmp_path / "original.txt"
    source.write_bytes(b"\xef\xbb\xbfHello.\r\n\r\n- World.\r\n")
    with PlainTextReader(source).iter_segments() as segments:
        proposals = [replace(s, text=s.text.replace("Hello", "Hallo")) for s in segments]
    return source, create_text_job(source, proposals, source_lang="en", target_lang="de")


def test_round_trip_preserves_source_proposals_and_identity(tmp_path):
    source, job = make_job(tmp_path)
    destination = tmp_path / "review.zip"
    save_job(job, destination)
    loaded = load_job(destination)
    assert loaded == job
    assert loaded.source == source.read_bytes()
    assert [b.id for b in loaded.blocks] == ["1", "2"]
    assert loaded.blocks[0].original == "Hello.\r\n"
    assert loaded.blocks[0].proposal == "Hallo.\r\n"
    assert loaded.blocks[1].type == "bullet_item"
    loaded.verify_source(source)
    source.write_text("Changed", encoding="utf-8")
    with pytest.raises(ReviewJobError, match="changed"):
        loaded.verify_source(source)
    source.unlink()
    assert load_job(destination) == job  # The snapshot is self-contained.
    with ZipFile(destination) as archive:
        assert b"\r\n" not in archive.read("job.json")


@pytest.mark.parametrize("kind", ["missing", "extra", "order", "type", "empty"])
def test_invalid_proposals_are_rejected(tmp_path, kind):
    source, job = make_job(tmp_path)
    values = [TextSegment(b.id, b.proposal, b.type) for b in job.blocks]
    if kind == "missing":
        values.pop()
    elif kind == "extra":
        values.append(values[0])
    elif kind == "order":
        values.reverse()
    elif kind == "type":
        values[0] = replace(values[0], type="heading")
    else:
        values[0] = replace(values[0], text=" ")
    with pytest.raises(ReviewJobError):
        create_text_job(source, values, source_lang="en", target_lang="de")


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": 2},
        {"schema_version": True},
        {"document_format": "odt"},
        {"id": "bad"},
        {"source_lang": ""},
        {"source_name": "../file"},
        {"source_name": "a\\b"},
        {"source_sha256": "bad"},
        {"blocks": ()},
    ],
)
def test_invalid_job_is_not_published(tmp_path, changes):
    _, job = make_job(tmp_path)
    output = tmp_path / "job.zip"
    with pytest.raises(ReviewJobError):
        save_job(replace(job, **changes), output)
    assert not output.exists()


def test_duplicate_and_modified_source_blocks_rejected(tmp_path):
    _, job = make_job(tmp_path)
    for blocks in (
        (job.blocks[0], job.blocks[0]),
        (replace(job.blocks[0], original="Changed"), job.blocks[1]),
    ):
        with pytest.raises(ReviewJobError, match="mismatch"):
            replace(job, blocks=blocks).validate()


def test_no_overwrite_and_publication_failure_cleanup(tmp_path, monkeypatch):
    from doc_lingo.review import storage

    _, job = make_job(tmp_path)
    output = tmp_path / "job.zip"
    output.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        save_job(job, output)
    assert output.read_bytes() == b"keep"
    output.unlink()

    def fail(*args):
        raise OSError("publication failed")

    monkeypatch.setattr(storage.os, "link", fail)
    with pytest.raises(OSError):
        save_job(job, output)
    assert not output.exists()
    assert not list(tmp_path.glob(".doc-lingo-review-*"))


@pytest.mark.parametrize(
    "kind",
    [
        "version",
        "missing",
        "unknown",
        "blocks",
        "block",
        "source",
        "hash",
        "json",
        "duplicate",
    ],
)
def test_malformed_stored_metadata(tmp_path, kind):
    _, job = make_job(tmp_path)
    path = tmp_path / "job.zip"
    save_job(job, path)
    with ZipFile(path) as archive:
        metadata = json.loads(archive.read("job.json"))
    if kind == "version":
        metadata["schema_version"] = 9
    elif kind == "missing":
        del metadata["schema_version"]
    elif kind == "unknown":
        metadata["other"] = 1
    elif kind == "blocks":
        metadata["blocks"] = None
    elif kind == "block":
        metadata["blocks"][0]["unexpected"] = 1
    elif kind == "source":
        metadata["source"] = "injected"
    elif kind == "hash":
        metadata["source_sha256"] = "incorrect"
    payload = json.dumps(metadata)
    if kind == "json":
        payload = "{"
    elif kind == "duplicate":
        payload = '{"id": 1, "id": 2}'
    with ZipFile(path, "w") as archive:
        archive.writestr("job.json", payload)
        archive.writestr("source.txt", job.source)
    with pytest.raises(ReviewJobError):
        load_job(path)


def test_archive_shape_limits_and_invalid_zip(tmp_path, monkeypatch):
    from doc_lingo.review import storage

    _, job = make_job(tmp_path)
    path = tmp_path / "job.zip"
    path.write_bytes(b"not a zip")
    with pytest.raises(ReviewJobError):
        load_job(path)
    with ZipFile(path, "w") as archive:
        archive.writestr("../outside", b"data")
    with pytest.raises(ReviewJobError, match="contain only"):
        load_job(path)
    path.unlink()
    save_job(job, path)
    monkeypatch.setattr(storage, "MAX_MEMBER_BYTES", 1)
    with pytest.raises(ReviewJobError, match="size limit"):
        load_job(path)
    with pytest.raises(ReviewJobError, match="size limit"):
        save_job(job, tmp_path / "large.zip")


def test_source_mutation_during_proposal_consumption(tmp_path):
    source, job = make_job(tmp_path)

    def proposals():
        for block in job.blocks:
            yield TextSegment(block.id, block.proposal, block.type)
        source.write_bytes(b"changed")

    with pytest.raises(ReviewJobError, match="changed"):
        create_text_job(source, proposals(), source_lang="en", target_lang="de")


def test_empty_source_and_unicode(tmp_path):
    source = tmp_path / "empty.txt"
    source.write_bytes(b"")
    job = create_text_job(source, [], source_lang="en", target_lang="de")
    save_job(job, tmp_path / "empty.zip")
    assert load_job(tmp_path / "empty.zip").blocks == ()
    source.write_text("Text.", encoding="utf-8")
    job = create_text_job(
        source, [TextSegment("1", "Grüße X0Z 🙂")], source_lang="en", target_lang="de"
    )
    save_job(job, tmp_path / "unicode.zip")
    assert load_job(tmp_path / "unicode.zip") == job
