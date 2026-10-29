"""Export TXT review jobs as editable four-row ODT tables."""

import os
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from doc_lingo.documents.odt.package import MIMETYPE, inspect_package
from doc_lingo.review.jobs import ReviewJob, ReviewJobError

NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
    "meta": "urn:oasis:names:tc:opendocument:xmlns:meta:1.0",
    "manifest": "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0",
}


def _name(value: str) -> str:
    prefix, local = value.split(":")
    return f"{{{NS[prefix]}}}{local}"


def _element(parent, name, **attributes):
    return ET.SubElement(parent, _name(name), {_name(k): v for k, v in attributes.items()})


def _xml(root):
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _paragraph(parent, text="", style="Body"):
    """Represent whitespace explicitly; TXT strings are never interpreted as XML."""
    if any(
        not (
            c in "\t\r\n"
            or 0x20 <= ord(c) <= 0xD7FF
            or 0xE000 <= ord(c) <= 0xFFFD
            or 0x10000 <= ord(c) <= 0x10FFFF
        )
        for c in text
    ):
        raise ReviewJobError("Review text contains characters not supported by XML")
    node = _element(parent, "text:p", **{"text:style-name": style})
    last = None
    for part in re.split(r"( +|\t|\n)", text.replace("\r\n", "\n").replace("\r", "\n")):
        if not part:
            continue
        if part.startswith(" "):
            last = _element(node, "text:s", **{"text:c": str(len(part))})
        elif part == "\t":
            last = _element(node, "text:tab")
        elif part == "\n":
            last = _element(node, "text:line-break")
        elif last is None:
            node.text = (node.text or "") + part
        else:
            last.tail = (last.tail or "") + part
    return node


def _styles():
    root = ET.Element(_name("office:document-styles"), {_name("office:version"): "1.3"})
    styles = _element(root, "office:styles")
    for name, bold, size in (
        ("Body", False, "11pt"),
        ("Label", True, "9pt"),
        ("Title", True, "16pt"),
    ):
        style = _element(styles, "style:style", **{"style:name": name, "style:family": "paragraph"})
        _element(style, "style:paragraph-properties", **{"fo:margin-bottom": "0.12cm"})
        _element(
            style,
            "style:text-properties",
            **{
                "fo:font-family": "Liberation Sans",
                "fo:font-size": size,
                "fo:font-weight": "bold" if bold else "normal",
            },
        )
    automatic = _element(root, "office:automatic-styles")
    layout = _element(automatic, "style:page-layout", **{"style:name": "Page"})
    _element(
        layout,
        "style:page-layout-properties",
        **{
            "fo:page-width": "21cm",
            "fo:page-height": "29.7cm",
            "fo:margin": "2cm",
        },
    )
    masters = _element(root, "office:master-styles")
    _element(
        masters,
        "style:master-page",
        **{
            "style:name": "Standard",
            "style:page-layout-name": "Page",
        },
    )
    return _xml(root)


def _content(job):
    root = ET.Element(_name("office:document-content"), {_name("office:version"): "1.3"})
    automatic = _element(root, "office:automatic-styles")
    for name, family, properties, attributes in (
        (
            "BlockTable",
            "table",
            "table-properties",
            {
                "style:width": "17cm",
                "table:align": "left",
                "fo:margin-bottom": "0.4cm",
                "style:may-break-between-rows": "true",
            },
        ),
        ("Column", "table-column", "table-column-properties", {"style:column-width": "17cm"}),
        (
            "Cell",
            "table-cell",
            "table-cell-properties",
            {
                "fo:border": "0.5pt solid #b0b0b0",
                "fo:padding": "0.2cm",
            },
        ),
        (
            "HeaderCell",
            "table-cell",
            "table-cell-properties",
            {
                "fo:border": "0.5pt solid #b0b0b0",
                "fo:padding": "0.2cm",
                "fo:background-color": "#e8edf2",
            },
        ),
        ("Row", "table-row", "table-row-properties", {"fo:keep-together": "auto"}),
        (
            "CorrectionRow",
            "table-row",
            "table-row-properties",
            {
                "style:min-row-height": "1.5cm",
                "fo:keep-together": "auto",
            },
        ),
    ):
        style = _element(automatic, "style:style", **{"style:name": name, "style:family": family})
        _element(style, "style:" + properties, **attributes)
    body = _element(_element(root, "office:body"), "office:text")
    _paragraph(body, "Translation review", "Title")
    _paragraph(body, f"{job.source_name} | {job.source_lang} → {job.target_lang}")
    _paragraph(
        body,
        "Edit only the Correction area. Leave it empty to accept the proposal. "
        "Keep block IDs and reference text unchanged. TXT output preserves text only; "
        "formatting added here will not become TXT formatting.",
    )
    for block in job.blocks:
        table = _element(
            body,
            "table:table",
            **{
                "table:name": f"DLBlock_{block.id}",
                "table:style-name": "BlockTable",
            },
        )
        _element(table, "table:table-column", **{"table:style-name": "Column"})
        for index, (label, value) in enumerate(
            (
                (f"Source: {job.source_name} | Block ID: {block.id}", None),
                ("Original", block.original),
                ("Machine translation", block.proposal),
                ("Correction", ""),
            )
        ):
            row = _element(
                table,
                "table:table-row",
                **{
                    "table:style-name": "CorrectionRow" if index == 3 else "Row",
                },
            )
            cell = _element(
                row,
                "table:table-cell",
                **{
                    "table:style-name": "HeaderCell" if index == 0 else "Cell",
                },
            )
            _paragraph(cell, label, "Label")
            if value is not None:
                _paragraph(cell, value)
        _paragraph(body)
    return _xml(root)


def _metadata(job):
    root = ET.Element(_name("office:document-meta"), {_name("office:version"): "1.3"})
    meta = _element(root, "office:meta")
    for key, value in {
        "doc-lingo.review-version": "1",
        "doc-lingo.job-id": job.id,
        "doc-lingo.source-sha256": job.source_sha256,
    }.items():
        entry = _element(
            meta,
            "meta:user-defined",
            **{
                "meta:name": key,
                "meta:value-type": "string",
            },
        )
        entry.text = value
    return _xml(root)


def export_review_odt(job: ReviewJob, destination: str | Path) -> None:
    """Export a validated TXT job without changing it or overwriting any file.

    Table names identify blocks; document properties identify the job and review
    schema. These identities still need an editor round trip before import exists.
    """
    job.validate()
    destination = Path(destination)
    if os.path.lexists(destination):
        raise FileExistsError(f"Review document already exists: {destination}")
    members = {"content.xml": _content(job), "styles.xml": _styles(), "meta.xml": _metadata(job)}
    manifest = ET.Element(_name("manifest:manifest"), {_name("manifest:version"): "1.3"})
    for name, media in [("/", MIMETYPE.decode()), *((name, "text/xml") for name in members)]:
        _element(
            manifest,
            "manifest:file-entry",
            **{
                "manifest:full-path": name,
                "manifest:media-type": media,
            },
        )
    members["META-INF/manifest.xml"] = _xml(manifest)
    with TemporaryDirectory(prefix=".doc-lingo-review-", dir=destination.parent) as directory:
        temporary = Path(directory) / "review.odt"
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("mimetype", MIMETYPE, compress_type=ZIP_STORED)
            for name, data in members.items():
                archive.writestr(name, data)
        inspect_package(temporary)
        os.link(temporary, destination)
