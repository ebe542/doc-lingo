"""Inspect an unencrypted ODT package without extraction or XML rewriting."""

from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile
from zlib import error as ZlibError

MIMETYPE = b"application/vnd.oasis.opendocument.text"
OFFICE = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
MANIFEST = "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
MAX_XML_BYTES = 16 * 1024 * 1024
MAX_PACKAGE_BYTES = 256 * 1024 * 1024


class OdtPackageError(ValueError):
    """The package is invalid or outside the currently supported ODT subset."""


@dataclass(frozen=True)
class OdtPackageInfo:
    """Inspection evidence, not a mutable XML tree or a translation session."""

    members: tuple[str, ...]
    content_xml: bytes
    styles_xml: bytes | None


class _NoDoctype(ET.TreeBuilder):
    def doctype(self, name, pubid, system):
        raise OdtPackageError("XML document type declarations are unsupported")


def _xml(data: bytes, root_name: str) -> ET.Element:
    try:
        root = ET.fromstring(data, parser=ET.XMLParser(target=_NoDoctype()))
    except ET.ParseError:
        raise OdtPackageError("Malformed ODT XML") from None
    if root.tag != root_name:
        raise OdtPackageError("Unexpected ODT XML root")
    return root


def inspect_package(source: str | Path) -> OdtPackageInfo:
    """Validate basic package structure; propagate ordinary filesystem errors.

    This is not full ODF schema or layout validation. No members are extracted,
    executed or rewritten. Limits bound declared uncompressed size and XML reads.
    """
    try:
        with Path(source).open("rb") as stream, ZipFile(stream) as archive:
            entries = archive.infolist()
            names = tuple(entry.filename for entry in entries)
            if len(set(names)) != len(names):
                raise OdtPackageError("Duplicate ODT archive member")
            for entry in entries:
                # ZipInfo normalizes separators on Windows and truncates NULs.
                # Validate the archived spelling before using normalized names.
                name = entry.orig_filename
                parts = name.rstrip("/").split("/")
                if (
                    "\x00" in name
                    or "\\" in name
                    or ":" in name
                    or any(p in ("", ".", "..") for p in parts)
                ):
                    raise OdtPackageError("Unsupported ODT archive member path")
                if entry.flag_bits & 1:
                    raise OdtPackageError("Encrypted ODT packages are unsupported")
                if entry.compress_type not in (ZIP_STORED, ZIP_DEFLATED):
                    raise OdtPackageError("Unsupported ODT compression method")
                if name.startswith("META-INF/") and "signatures" in name.lower():
                    raise OdtPackageError("Signed ODT packages are unsupported")
            if sum(entry.file_size for entry in entries) > MAX_PACKAGE_BYTES:
                raise OdtPackageError("ODT package exceeds the inspection size limit")
            if not {"mimetype", "content.xml", "META-INF/manifest.xml"}.issubset(names):
                raise OdtPackageError("Missing required ODT package member")
            mime = archive.getinfo("mimetype")
            if entries[0] != mime or mime.header_offset != 0 or mime.compress_type != ZIP_STORED:
                raise OdtPackageError("ODT mimetype must be the first uncompressed member")
            if mime.file_size != len(MIMETYPE) or archive.read(mime) != MIMETYPE:
                raise OdtPackageError("Package is not an ODT text document")
            stream.seek(0)
            header = stream.read(30)
            if len(header) != 30 or header[28:30] != b"\x00\x00":
                raise OdtPackageError("ODT mimetype header must not contain extra fields")

            def read_xml(name):
                if archive.getinfo(name).file_size > MAX_XML_BYTES:
                    raise OdtPackageError("ODT XML exceeds the inspection size limit")
                with archive.open(name) as stream:
                    data = stream.read(MAX_XML_BYTES + 1)
                if len(data) > MAX_XML_BYTES:
                    raise OdtPackageError("ODT XML exceeds the inspection size limit")
                return data

            manifest = _xml(read_xml("META-INF/manifest.xml"), f"{{{MANIFEST}}}manifest")
            if any(
                element.tag in (f"{{{MANIFEST}}}encryption-data", f"{{{MANIFEST}}}encrypted-key")
                for element in manifest.iter()
            ):
                raise OdtPackageError("Encrypted ODT packages are unsupported")
            declared = {}
            for entry in manifest.findall(f"{{{MANIFEST}}}file-entry"):
                path = entry.get(f"{{{MANIFEST}}}full-path")
                if path is None or path in declared:
                    raise OdtPackageError("Missing or duplicate ODT manifest path")
                declared[path] = entry.get(f"{{{MANIFEST}}}media-type")
                if path != "/" and not path.endswith("/") and path not in names:
                    raise OdtPackageError("Manifest references a missing ODT member")
            if declared.get("/") != MIMETYPE.decode() or declared.get("content.xml") != "text/xml":
                raise OdtPackageError("ODT manifest document type does not match")
            content = read_xml("content.xml")
            root = _xml(content, f"{{{OFFICE}}}document-content")
            bodies = root.findall(f"{{{OFFICE}}}body")
            if len(bodies) != 1 or [child.tag for child in bodies[0]] != [f"{{{OFFICE}}}text"]:
                raise OdtPackageError("ODT content must contain one text body")
            styles = read_xml("styles.xml") if "styles.xml" in names else None
            if styles is not None:
                if declared.get("styles.xml") != "text/xml":
                    raise OdtPackageError("ODT styles are missing from the manifest")
                _xml(styles, f"{{{OFFICE}}}document-styles")
            return OdtPackageInfo(names, content, styles)
    except (BadZipFile, EOFError, ZlibError):
        raise OdtPackageError("Invalid or damaged ODT ZIP package") from None
