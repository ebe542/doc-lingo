"""Read-only validation of synthetic ODT packages and unsupported inputs."""

from zipfile import ZIP_BZIP2, ZIP_DEFLATED, ZipFile

import pytest

from doc_lingo.documents.odt import OdtPackageError, inspect_package


def test_inspection_keeps_source_and_member_bytes(odt_factory):
    path = odt_factory()
    original = path.read_bytes()
    result = inspect_package(path)
    with ZipFile(path) as archive:
        assert result.content_xml == archive.read("content.xml")
        assert result.styles_xml == archive.read("styles.xml")
        assert result.members == tuple(archive.namelist())
    assert path.read_bytes() == original
    # Closed handles allow a rename on Windows.
    path.rename(path.with_suffix(".renamed"))


@pytest.mark.parametrize("name", ["mimetype", "content.xml", "META-INF/manifest.xml"])
def test_missing_required_part(odt_factory, name):
    with pytest.raises(OdtPackageError, match="Missing required"):
        inspect_package(odt_factory(omit=(name,)))


def test_wrong_document_type(odt_factory):
    with pytest.raises(OdtPackageError, match="not an ODT"):
        inspect_package(
            odt_factory(updates={"mimetype": b"application/vnd.oasis.opendocument.presentation"})
        )


def test_compressed_mimetype(odt_factory):
    with pytest.raises(OdtPackageError, match="first uncompressed"):
        inspect_package(odt_factory(mime_compression=ZIP_DEFLATED))


@pytest.mark.parametrize(
    "change,message",
    [
        ("extra", "extra fields"),
        ("compression", "compression method"),
        ("order", "first uncompressed"),
    ],
)
def test_archive_header_rules(odt_factory, change, message):
    path = odt_factory()
    with ZipFile(path) as archive:
        members = [(info, archive.read(info)) for info in archive.infolist()]
    if change == "extra":
        members[0][0].extra = b"\xfe\xca\x00\x00"
    elif change == "compression":
        members[1][0].compress_type = ZIP_BZIP2
    else:
        members[0], members[1] = members[1], members[0]
    with ZipFile(path, "w") as archive:
        for info, data in members:
            archive.writestr(info, data)
    with pytest.raises(OdtPackageError, match=message):
        inspect_package(path)


@pytest.mark.parametrize("name", ["../outside", "/absolute", "a\\b", "a//b", "C:part"])
def test_unsupported_member_paths(odt_factory, name):
    if "\\" in name:
        # Patch both ZIP headers after writing: ZipInfo otherwise normalizes
        # the invalid name before it ever reaches the package inspector.
        path = odt_factory(extra=(("a/b", b"data"),))
        raw = path.read_bytes()
        assert raw.count(b"a/b") == 2
        path.write_bytes(raw.replace(b"a/b", b"a\\b"))
    else:
        path = odt_factory(extra=((name, b"data"),))
    with pytest.raises(OdtPackageError, match="member path"):
        inspect_package(path)


def test_duplicate_members(odt_factory):
    with pytest.warns(UserWarning, match="Duplicate name"):
        path = odt_factory(extra=(("content.xml", b"other"),))
    with pytest.raises(OdtPackageError, match="Duplicate"):
        inspect_package(path)


def test_signed_package(odt_factory):
    with pytest.raises(OdtPackageError, match="Signed"):
        inspect_package(odt_factory(extra=(("META-INF/documentsignatures.xml", b"signature"),)))


@pytest.mark.parametrize(
    "payload, message",
    [
        (b"<broken", "Malformed"),
        (b"<wrong/>", "Unexpected"),
        (b'<!DOCTYPE x [<!ENTITY word "expanded">]><x>&word;</x>', "type declarations"),
    ],
)
def test_invalid_xml(odt_factory, payload, message):
    with pytest.raises(OdtPackageError, match=message):
        inspect_package(odt_factory(updates={"content.xml": payload}))


def rewrite(path, name, transform):
    with ZipFile(path) as archive:
        members = [(info, archive.read(info)) for info in archive.infolist()]
    with ZipFile(path, "w") as archive:
        for info, data in members:
            archive.writestr(info, transform(data) if info.filename == name else data)


@pytest.mark.parametrize(
    "old,new,message",
    [
        (b"office:text", b"office:presentation", "one text body"),
        (b"office:body", b"office:other", "one text body"),
    ],
)
def test_wrong_body(odt_factory, old, new, message):
    path = odt_factory()
    rewrite(path, "content.xml", lambda data: data.replace(old, new))
    with pytest.raises(OdtPackageError, match=message):
        inspect_package(path)


@pytest.mark.parametrize(
    "transform,message",
    [
        (
            lambda d: d.replace(
                b"</manifest:manifest>", b"<manifest:encryption-data/></manifest:manifest>"
            ),
            "Encrypted",
        ),
        (
            lambda d: d.replace(b'full-path="content.xml"', b'full-path="absent.xml"'),
            "missing ODT member",
        ),
        (lambda d: d.replace(b'full-path="content.xml"', b'full-path="/"'), "duplicate"),
        (
            lambda d: d.replace(b'full-path="content.xml"', b'other="content.xml"'),
            "Missing or duplicate",
        ),
        (lambda d: d.replace(b'full-path="/"', b'full-path="unused/"'), "does not match"),
        (
            lambda d: d.replace(b'full-path="styles.xml"', b'full-path="unused/"'),
            "styles are missing",
        ),
    ],
)
def test_invalid_manifest(odt_factory, transform, message):
    path = odt_factory()
    rewrite(path, "META-INF/manifest.xml", transform)
    with pytest.raises(OdtPackageError, match=message):
        inspect_package(path)


def test_optional_styles(odt_factory):
    path = odt_factory(omit=("styles.xml",))
    rewrite(
        path,
        "META-INF/manifest.xml",
        lambda d: d.replace(b'full-path="styles.xml"', b'full-path="unused/"'),
    )
    assert inspect_package(path).styles_xml is None


@pytest.mark.parametrize("limit", ["MAX_XML_BYTES", "MAX_PACKAGE_BYTES"])
def test_size_limits(odt_factory, monkeypatch, limit):
    from doc_lingo.documents.odt import package

    monkeypatch.setattr(package, limit, 10)
    with pytest.raises(OdtPackageError, match="size limit"):
        inspect_package(odt_factory())


def test_bad_zip_and_missing_file(tmp_path):
    path = tmp_path / "not.odt"
    with pytest.raises(FileNotFoundError):
        inspect_package(path)
    path.write_bytes(b"not a zip")
    with pytest.raises(OdtPackageError, match="ZIP"):
        inspect_package(path)
