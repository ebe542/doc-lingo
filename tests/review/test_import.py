"""Review import validates evidence before publishing selected TXT translations."""

from copy import deepcopy
from dataclasses import replace
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from doc_lingo import PlainTextReader
from doc_lingo.review import (
    ReviewJobError,
    create_text_job,
    export_review_odt,
    finalize_text_review,
    import_review_odt,
)
from doc_lingo.review.odt import NS, _name


def setup_review(tmp_path):
    source = tmp_path / "source.txt"
    source.write_bytes(b"\xef\xbb\xbfHello.\r\n\r\n- World.\r\n")
    with PlainTextReader(source).iter_segments() as values:
        proposals = [
            replace(s, text=s.text.replace("Hello", "Hallo").replace("World", "Welt"))
            for s in values
        ]
    job = create_text_job(source, proposals, source_lang="en", target_lang="de")
    review = tmp_path / "review.odt"
    export_review_odt(job, review)
    return job, source, review


def edit(review, change, part="content.xml"):
    with ZipFile(review) as archive:
        members = [(info, archive.read(info)) for info in archive.infolist()]
    with ZipFile(review, "w") as archive:
        for info, data in members:
            if info.filename == part:
                root = ET.fromstring(data)
                change(root)
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            archive.writestr(info, data)


def cell(root, block=0, row=3):
    table = root.findall(".//table:table", NS)[block]
    return table.findall("table:table-row", NS)[row][0]


def test_unchanged_review_accepts_proposals_and_preserves_structure(tmp_path):
    job, source, review = setup_review(tmp_path)
    before = review.read_bytes()
    output = tmp_path / "out.txt"
    finalize_text_review(job, review, output, original=source)
    assert output.read_bytes() == b"\xef\xbb\xbfHallo.\r\n\r\n- Welt.\r\n"
    assert review.read_bytes() == before
    assert not list(tmp_path.glob(".doc-lingo-*"))


def test_corrections_and_reordered_tables_are_restored_in_source_order(tmp_path):
    job, source, review = setup_review(tmp_path)

    def change(root):
        area = cell(root, block=1)
        area[1].text = "Meine "
        span = ET.SubElement(area[1], _name("text:span"))
        span.text = "Korrektur"
        ET.SubElement(area[1], _name("text:tab")).tail = "& <Text>"
        ET.SubElement(area, _name("text:p")).text = "Zweite Zeile."
        body = root.find("office:body/office:text", NS)
        tables = body.findall("table:table", NS)
        for table in tables:
            body.remove(table)
        body.extend(reversed(tables))

    edit(review, change)
    values = import_review_odt(job, review)
    assert values[0].text == job.blocks[0].proposal
    assert values[1].text == "Meine Korrektur\t& <Text>\nZweite Zeile."
    source.unlink()  # Finalization uses the retained snapshot.
    output = tmp_path / "out.txt"
    finalize_text_review(job, review, output)
    assert output.read_bytes() == (
        b"\xef\xbb\xbfHallo.\r\n\r\n- Meine Korrektur\t& <Text>\nZweite Zeile.\r\n"
    )


def test_whitespace_only_correction_accepts_saved_proposal(tmp_path):
    job, _, review = setup_review(tmp_path)
    edit(review, lambda root: setattr(cell(root)[1], "text", " \t\n"))
    assert import_review_odt(job, review)[0].text == job.blocks[0].proposal


@pytest.mark.parametrize(
    "kind",
    [
        "missing",
        "duplicate",
        "unknown",
        "reference",
        "proposal",
        "label",
        "row",
        "column",
        "repeat",
        "merged",
        "object",
        "tracked",
        "outside",
        "list",
        "space",
        "field",
    ],
)
def test_invalid_review_never_publishes(tmp_path, kind):
    job, _, review = setup_review(tmp_path)

    def change(root):
        body = root.find("office:body/office:text", NS)
        table = body.find("table:table", NS)
        if kind == "missing":
            body.remove(table)
        elif kind == "duplicate":
            body.append(deepcopy(table))
        elif kind == "unknown":
            table.set(_name("table:name"), "Other")
        elif kind in ("reference", "proposal"):
            cell(root, row=1 if kind == "reference" else 2)[1].text = "Changed"
        elif kind == "label":
            cell(root)[0].text = "Changed label"
        elif kind == "row":
            table.remove(table.findall("table:table-row", NS)[0])
        elif kind == "column":
            table.append(ET.Element(_name("table:table-column")))
        elif kind == "repeat":
            table.findall("table:table-row", NS)[0].set(_name("table:number-rows-repeated"), "2")
        elif kind == "merged":
            cell(root).set(_name("table:number-columns-spanned"), "2")
        elif kind == "object":
            ET.SubElement(cell(root)[1], _name("office:annotation"))
        elif kind == "tracked":
            ET.SubElement(body, _name("text:tracked-changes"))
        elif kind == "outside":
            ET.SubElement(body, _name("text:p")).text = "Unassigned correction"
        elif kind == "list":
            ET.SubElement(cell(root), _name("text:list"))
        elif kind == "space":
            ET.SubElement(cell(root)[1], _name("text:s"), {_name("text:c"): "-1"})
        else:
            ET.SubElement(cell(root)[1], _name("text:page-number")).text = "1"

    edit(review, change)
    output = tmp_path / "out.txt"
    with pytest.raises(ReviewJobError):
        finalize_text_review(job, review, output)
    assert not output.exists()
    assert not list(tmp_path.glob(".doc-lingo-*"))


@pytest.mark.parametrize("kind", ["job", "hash", "version", "duplicate", "missing"])
def test_metadata_must_bind_to_job(tmp_path, kind):
    job, _, review = setup_review(tmp_path)

    def change(root):
        meta = root.find("office:meta", NS)
        if kind == "duplicate":
            meta.append(deepcopy(meta[0]))
        elif kind == "missing":
            meta.remove(meta[0])
        else:
            name = {"job": "job-id", "hash": "source-sha256", "version": "review-version"}[kind]
            for child in meta:
                if child.get(_name("meta:name")) == "doc-lingo." + name:
                    child.text = "changed"

    edit(review, change, "meta.xml")
    with pytest.raises(ReviewJobError, match="metadata|identity|fingerprint"):
        import_review_odt(job, review)


def test_editor_bookmarks_spans_and_soft_breaks_preserve_reference_text(tmp_path):
    job, _, review = setup_review(tmp_path)

    def change(root):
        p = cell(root, row=1)[1]
        text = p.text
        p.text = None
        span = ET.Element(_name("text:span"))
        span.text = text
        p.insert(0, span)
        ET.SubElement(p, _name("text:soft-page-break"))
        ET.SubElement(p, _name("text:bookmark"), {_name("text:name"): "Editor"})
        declarations = ET.SubElement(
            root.find("office:body/office:text", NS), _name("text:sequence-decls")
        )
        ET.SubElement(declarations, _name("text:sequence-decl"), {_name("text:name"): "Figure"})

    edit(review, change)
    assert [s.text for s in import_review_odt(job, review)] == [b.proposal for b in job.blocks]


def test_changed_original_and_existing_output_are_preserved(tmp_path):
    job, source, review = setup_review(tmp_path)
    output = tmp_path / "out.txt"
    output.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        finalize_text_review(job, review, output)
    assert output.read_bytes() == b"keep"
    output.unlink()
    source.write_bytes(b"changed")
    with pytest.raises(ReviewJobError, match="changed"):
        finalize_text_review(job, review, output, original=source)
    assert not output.exists()


def test_empty_job_can_be_finalized(tmp_path):
    source = tmp_path / "empty.txt"
    source.write_bytes(b"")
    job = create_text_job(source, [], source_lang="en", target_lang="de")
    review = tmp_path / "empty.odt"
    export_review_odt(job, review)
    output = tmp_path / "out.txt"
    finalize_text_review(job, review, output)
    assert output.read_bytes() == b""


def test_metadata_doctype_is_rejected(tmp_path):
    job, _, review = setup_review(tmp_path)
    with ZipFile(review) as archive:
        members = [(info, archive.read(info)) for info in archive.infolist()]
    with ZipFile(review, "w") as archive:
        for info, data in members:
            if info.filename == "meta.xml":
                data = data.replace(b"?>", b'?><!DOCTYPE x [<!ENTITY hidden "value">]>', 1)
            archive.writestr(info, data)
    with pytest.raises(ReviewJobError, match="type declarations"):
        import_review_odt(job, review)


def test_finalization_publication_failure_removes_temporary_snapshot(tmp_path, monkeypatch):
    from doc_lingo.documents.plain_text import writer

    job, _, review = setup_review(tmp_path)
    before = review.read_bytes()

    def fail(*args):
        raise OSError("publication failed")

    monkeypatch.setattr(writer.os, "link", fail)
    output = tmp_path / "out.txt"
    with pytest.raises(OSError):
        finalize_text_review(job, review, output)
    assert not output.exists()
    assert not list(tmp_path.glob(".doc-lingo-*"))
    assert review.read_bytes() == before
