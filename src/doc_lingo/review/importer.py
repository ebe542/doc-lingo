"""Strict text-only import of schema-1 ODT review documents."""

from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from doc_lingo.documents.models import TextSegment
from doc_lingo.documents.odt.package import MAX_XML_BYTES, inspect_package
from doc_lingo.review.jobs import ReviewJob, ReviewJobError
from doc_lingo.review.odt import NS, _content, _name


class _NoDoctype(ET.TreeBuilder):
    def doctype(self, name, pubid, system):
        raise ReviewJobError("Document type declarations are not supported in reviews")


def _parse(data):
    try:
        return ET.fromstring(data, parser=ET.XMLParser(target=_NoDoctype()))
    except ET.ParseError:
        raise ReviewJobError("Malformed review XML") from None


def _plain(node):
    """Read supported editor inline text; reject content that TXT would lose."""
    result = [node.text or ""]
    spaces = 0
    for child in node:
        if child.tag in (_name("text:span"), _name("text:a")):
            result.append(_plain(child))
        elif child.tag == _name("text:s"):
            count = child.get(_name("text:c"), "1")
            if (
                len(count) > 6
                or not count.isascii()
                or not count.isdecimal()
                or not 1 <= int(count) <= 100000
            ):
                raise ReviewJobError("Invalid or excessive space count in review text")
            spaces += int(count)
            if spaces > MAX_XML_BYTES:
                raise ReviewJobError("Expanded review whitespace exceeds size limit")
            result.append(" " * int(count))
        elif child.tag == _name("text:tab"):
            result.append("\t")
        elif child.tag == _name("text:line-break"):
            result.append("\n")
        elif child.tag not in {
            _name("text:bookmark"),
            _name("text:bookmark-start"),
            _name("text:bookmark-end"),
            _name("text:soft-page-break"),
        }:
            raise ReviewJobError(
                "Unsupported review content; use plain text without fields or objects"
            )
        if child.tag not in (_name("text:span"), _name("text:a")) and (len(child) or child.text):
            raise ReviewJobError("Unexpected content in a review text marker")
        result.append(child.tail or "")
    return "".join(result)


def _paragraphs(cell):
    if (cell.text or "").strip() or any((p.tail or "").strip() for p in cell):
        raise ReviewJobError("Review cell contains text outside paragraphs")
    if any(p.tag != _name("text:p") for p in cell):
        raise ReviewJobError("Review areas must contain paragraphs, not lists, tables or objects")
    return [_plain(p) for p in cell]


def _single_extent(node):
    for attr in (
        "number-columns-repeated",
        "number-rows-repeated",
        "number-columns-spanned",
        "number-rows-spanned",
    ):
        if node.get(_name("table:" + attr), "1") != "1":
            raise ReviewJobError("Repeated or merged review rows/cells are not supported")


def _rows(table):
    _single_extent(table)
    if any(n.tag not in (_name("table:table-column"), _name("table:table-row")) for n in table):
        raise ReviewJobError("Review table structure changed")
    columns = table.findall("table:table-column", NS)
    if len(columns) != 1:
        raise ReviewJobError("Review tables must have one column")
    _single_extent(columns[0])
    rows = table.findall("table:table-row", NS)
    if len(rows) != 4:
        raise ReviewJobError("Review tables must have four rows")
    result = []
    for row in rows:
        _single_extent(row)
        if len(row) != 1 or row[0].tag != _name("table:table-cell"):
            raise ReviewJobError("Review rows must have one cell")
        _single_extent(row[0])
        result.append(_paragraphs(row[0]))
    return result


def _check_metadata(job, data):
    root = _parse(data)
    if root.tag != _name("office:document-meta"):
        raise ReviewJobError("Invalid review metadata root")
    expected = {
        "doc-lingo.review-version": "1",
        "doc-lingo.job-id": job.id,
        "doc-lingo.source-sha256": job.source_sha256,
    }
    found = {}
    for node in root.findall("office:meta/meta:user-defined", NS):
        name = node.get(_name("meta:name"))
        if name in expected:
            if (
                name in found
                or len(node)
                or node.get(_name("meta:value-type"), "string") != "string"
            ):
                raise ReviewJobError("Duplicate or invalid review identity metadata")
            found[name] = node.text
    if found != expected:
        raise ReviewJobError("Review version, job identity or source fingerprint does not match")


def import_review_odt(job: ReviewJob, source: str | Path) -> tuple[TextSegment, ...]:
    """Select corrections or saved proposals, in original job order.

    Formatting is intentionally text-only for TXT. Unsupported embedded content,
    tracked changes, modified reference text and incomplete IDs fail explicitly.
    """
    job.validate()
    package = inspect_package(source)
    with ZipFile(source) as archive:
        if "meta.xml" not in archive.namelist():
            raise ReviewJobError("Review identity metadata is missing")
        if archive.getinfo("meta.xml").file_size > MAX_XML_BYTES:
            raise ReviewJobError("Review metadata exceeds size limit")
        with archive.open("meta.xml") as stream:
            data = stream.read(MAX_XML_BYTES + 1)
        if len(data) > MAX_XML_BYTES:
            raise ReviewJobError("Review metadata exceeds size limit")
        _check_metadata(job, data)
    body = _parse(package.content_xml).find("office:body/office:text", NS)
    assert body is not None  # Package inspection requires exactly one text body.
    if body.find(".//text:tracked-changes", NS) is not None:
        raise ReviewJobError("Accept or reject tracked changes before importing the review")
    expected_body = _parse(_content(job)).find("office:body/office:text", NS)
    assert expected_body is not None
    expected_tables = {
        t.get(_name("table:name")): t for t in expected_body.findall("table:table", NS)
    }
    expected_intro = [_plain(p) for p in expected_body.findall("text:p", NS) if _plain(p).strip()]
    intro = []
    selected = {}
    for node in body:
        if node.tag == _name("text:p"):
            text = _plain(node)
            if text.strip():
                intro.append(text)
            continue
        if node.tag == _name("text:sequence-decls"):
            # Writer inserts sequence definitions on save; they contain no body text.
            if any(
                n.tag != _name("text:sequence-decl") or len(n) or (n.text or "").strip()
                for n in node
            ):
                raise ReviewJobError("Unsupported review declarations")
            continue
        if node.tag != _name("table:table"):
            raise ReviewJobError("Unexpected content outside review tables")
        name = node.get(_name("table:name"))
        if name not in expected_tables or name in selected:
            raise ReviewJobError("Unknown or duplicate review block ID")
        try:
            rows = _rows(node)
            expected = _rows(expected_tables[name])
            if rows[:3] != expected[:3]:
                raise ReviewJobError("Reference text changed; move edits into the Correction area")
            if not rows[3] or rows[3][0] != "Correction":
                raise ReviewJobError("Correction label is missing or changed")
            selected[name] = "\n".join(rows[3][1:])
        except ReviewJobError as error:
            raise ReviewJobError(f"{name}: {error}") from error
    if intro != expected_intro:
        raise ReviewJobError("Review heading/instructions changed or text was added outside blocks")
    if selected.keys() != expected_tables.keys():
        raise ReviewJobError("Review contains missing blocks")
    return tuple(
        TextSegment(
            block.id,
            selected[f"DLBlock_{block.id}"]
            if selected[f"DLBlock_{block.id}"].strip()
            else block.proposal,
            block.type,
        )
        for block in job.blocks
    )
