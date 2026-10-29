"""Review ODT structure and publication, independent of models and editors."""

from dataclasses import replace
from xml.etree import ElementTree as ET
from zipfile import ZIP_STORED, ZipFile

import pytest

from doc_lingo import PlainTextReader
from doc_lingo.documents.odt import inspect_package
from doc_lingo.review import ReviewJobError, create_text_job, export_review_odt, load_job, save_job
from doc_lingo.review.odt import NS


def job_for(tmp_path, text="Hello.\n\nWorld.\n"):
    source = tmp_path / "input.txt"
    source.write_text(text, encoding="utf-8", newline="")
    with PlainTextReader(source).iter_segments() as values:
        return create_text_job(
            source,
            [replace(s, text="Übersetzt: " + s.text) for s in values],
            source_lang="en",
            target_lang="de",
        )


def plain(node):
    """Decode ODF whitespace without conflating labels with payload paragraphs."""
    value = node.text or ""
    for child in node:
        if child.tag == f"{{{NS['text']}}}s":
            value += " " * int(child.get(f"{{{NS['text']}}}c", "1"))
        elif child.tag == f"{{{NS['text']}}}tab":
            value += "\t"
        elif child.tag == f"{{{NS['text']}}}line-break":
            value += "\n"
        else:
            value += plain(child)
        value += child.tail or ""
    return value


def test_saved_job_exports_four_rows_with_separate_labels_and_identity(tmp_path):
    job = job_for(tmp_path)
    saved = tmp_path / "job.zip"
    save_job(job, saved)
    before = saved.read_bytes()
    output = tmp_path / "review.odt"
    export_review_odt(load_job(saved), output)
    assert saved.read_bytes() == before
    inspect_package(output)
    with ZipFile(output) as archive:
        assert archive.infolist()[0].filename == "mimetype"
        assert archive.infolist()[0].compress_type == ZIP_STORED
        root = ET.fromstring(archive.read("content.xml"))
        metadata = ET.fromstring(archive.read("meta.xml"))
    tables = root.findall(".//table:table", NS)
    assert len(tables) == len(job.blocks)
    for table, block in zip(tables, job.blocks, strict=True):
        assert table.get(f"{{{NS['table']}}}name") == f"DLBlock_{block.id}"
        rows = table.findall("table:table-row", NS)
        assert len(rows) == 4
        paragraphs = [row.findall("table:table-cell/text:p", NS) for row in rows]
        assert len(paragraphs[0]) == 1
        assert f"Block ID: {block.id}" in plain(paragraphs[0][0])
        assert "Page" not in plain(paragraphs[0][0])
        assert [plain(paragraphs[i][0]) for i in (1, 2, 3)] == [
            "Original",
            "Machine translation",
            "Correction",
        ]
        assert plain(paragraphs[1][1]) == block.original
        assert plain(paragraphs[2][1]) == block.proposal
        assert plain(paragraphs[3][1]) == ""
    properties = {
        n.get(f"{{{NS['meta']}}}name"): n.text for n in metadata.findall(".//meta:user-defined", NS)
    }
    assert properties == {
        "doc-lingo.review-version": "1",
        "doc-lingo.job-id": job.id,
        "doc-lingo.source-sha256": job.source_sha256,
    }
    assert root.find(".//text:user-field-decls", NS) is None


@pytest.mark.parametrize(
    "text",
    [
        '  Hello\t <tag> & "quotes" X0Z 🙂.\r\nSecond line.\r\n',
        "Hello.\rSecond line.\r",
        "Long text " * 3000,
    ],
)
def test_text_is_escaped_and_whitespace_is_preserved(tmp_path, text):
    job = job_for(tmp_path, text)
    output = tmp_path / "review.odt"
    export_review_odt(job, output)
    with ZipFile(output) as archive:
        root = ET.fromstring(archive.read("content.xml"))
    rows = root.findall(".//table:table", NS)[0].findall("table:table-row", NS)
    original = rows[1].findall("table:table-cell/text:p", NS)[1]
    assert plain(original) == job.blocks[0].original.replace("\r\n", "\n").replace("\r", "\n")
    assert original.find("tag") is None


def test_empty_job_exports_document_without_tables(tmp_path):
    output = tmp_path / "review.odt"
    export_review_odt(job_for(tmp_path, ""), output)
    with ZipFile(output) as archive:
        root = ET.fromstring(archive.read("content.xml"))
    assert root.findall(".//table:table", NS) == []


def test_no_overwrite_invalid_text_and_cleanup(tmp_path, monkeypatch):
    from doc_lingo.review import odt

    job = job_for(tmp_path)
    output = tmp_path / "review.odt"
    output.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        export_review_odt(job, output)
    assert output.read_bytes() == b"keep"
    output.unlink()
    invalid = replace(job, blocks=(replace(job.blocks[0], proposal="bad\x00"), *job.blocks[1:]))
    with pytest.raises(ReviewJobError, match="XML"):
        export_review_odt(invalid, output)
    assert not output.exists()

    def fail(*args):
        raise OSError("cannot publish")

    monkeypatch.setattr(odt.os, "link", fail)
    with pytest.raises(OSError):
        export_review_odt(job, output)
    assert not output.exists()
    assert not list(tmp_path.glob(".doc-lingo-review-*"))
