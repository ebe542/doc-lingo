"""Model-free ODT subset round trips and precise source-byte preservation."""

from dataclasses import replace
from zipfile import ZipFile

import pytest

from doc_lingo import SegmentMismatchError, translate_document
from doc_lingo.documents.odt import OdtPackageError, OdtReader, OdtWriter
from doc_lingo.documents.odt.blocks import text_blocks


def segments(path):
    with OdtReader(path).iter_segments() as values:
        return list(values)


def test_reader_subset_and_skipped_inventory(odt_factory):
    reader = OdtReader(odt_factory())
    with reader.iter_segments() as values:
        result = list(values)
        assert result[1].id == "2"
        assert result[1].protected_spans
        assert [(s.id, s.text, s.type) for s in result if s.id != "2"] == [
            ("1", "Example", "heading"),
            ("3", "First", "list_item"),
            ("4", "Nested", "list_item"),
            ("5", "Cell one", "paragraph"),
            ("6", "Cell two", "paragraph"),
        ]
    assert [(b.segment.id, b.reason) for b in reader.skipped_blocks] == [
        ("7", "protected_only"),
    ]
    with reader.iter_segments() as values:
        assert next(values).id == "1"
    assert list(values) == []


def test_round_trip_preserves_every_member_payload(odt_factory, tmp_path):
    path = odt_factory()
    original = path.read_bytes()
    output = tmp_path / "out.odt"
    OdtWriter(path).write(output, segments(path))
    with ZipFile(path) as source, ZipFile(output) as target:
        assert source.namelist() == target.namelist()
        assert source.comment == target.comment
        for name in source.namelist():
            assert source.read(name) == target.read(name)
    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".doc-lingo-*"))


def test_changed_text_is_escaped_without_serializing_xml(odt_factory, tmp_path):
    path = odt_factory()
    values = segments(path)
    values[0] = replace(values[0], text="Äpfel & <Birnen>")
    output = tmp_path / "out.odt"
    OdtWriter(path).write(output, values)
    with ZipFile(path) as source, ZipFile(output) as target:
        assert target.read("content.xml") == source.read("content.xml").replace(
            b">Example<",
            ">Äpfel &amp; &lt;Birnen&gt;<".encode(),
        )
        for name in source.namelist():
            if name != "content.xml":
                assert source.read(name) == target.read(name)
    assert segments(output)[0].text == "Äpfel & <Birnen>"


@pytest.mark.parametrize("mode", ["missing", "extra", "order", "type"])
def test_mismatch_never_publishes(odt_factory, tmp_path, mode):
    path = odt_factory()
    values = segments(path)
    if mode == "missing":
        values.pop()
    elif mode == "extra":
        values.append(values[-1])
    elif mode == "order":
        values.reverse()
    else:
        values[0] = replace(values[0], type="paragraph")
    output = tmp_path / "out.odt"
    with pytest.raises(SegmentMismatchError):
        OdtWriter(path).write(output, values)
    assert not output.exists()


@pytest.mark.parametrize("text", ["", "\x00", "x\ud800", "a\nb", "a\tb", "two  spaces"])
def test_unsupported_translation_never_publishes(odt_factory, tmp_path, text):
    path = odt_factory()
    values = segments(path)
    values[0] = replace(values[0], text=text)
    output = tmp_path / "out.odt"
    with pytest.raises(OdtPackageError):
        OdtWriter(path).write(output, values)
    assert not output.exists()


def test_existing_destination_untouched(odt_factory, tmp_path):
    path = odt_factory()
    output = tmp_path / "out.odt"
    output.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        OdtWriter(path).write(output, [])
    assert output.read_bytes() == b"keep"


def test_service_can_process_subset_without_models(odt_factory, tmp_path):
    class Upper:
        def translate(self, text, **kwargs):
            for word in ("Example", "First", "Nested", "formatted"):
                text = text.replace(word, word.upper())
            return text

    path = odt_factory()
    output = tmp_path / "out.odt"
    translate_document(
        OdtReader(path), OdtWriter(path), Upper(), output, source_lang="en", target_lang="de"
    )
    result = segments(output)
    assert "FORMATTED" in result[1].text
    assert [s.text for s in result if s.id != "2"] == [
        "EXAMPLE",
        "FIRST",
        "NESTED",
        "Cell one",
        "Cell two",
    ]


def test_xml_offsets_handle_prefix_aliases_entities_and_quotes():
    xml = b"""<o:document-content xmlns:o="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
    xmlns:t="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><o:body><o:text>
    <t:p t:style-name="a&gt;b">caf&#233; &amp; tea</t:p><t:p/><t:p> </t:p>
    <t:p>keep<!-- comment -->this</t:p><t:p><![CDATA[keep]]></t:p>
    </o:text></o:body></o:document-content>"""
    blocks = text_blocks(xml)
    assert blocks[0].segment.text == "café & tea"
    assert xml[blocks[0].start : blocks[0].end] == b"caf&#233; &amp; tea"
    assert [b.reason for b in blocks[1:]] == ["empty", "empty", "inline_content", "inline_content"]


@pytest.mark.parametrize(
    "xml",
    [
        b"\xff",
        b"<x",
        b'<?xml version="1.0" encoding="ISO-8859-1"?><x/>',
        "<x/>".encode("utf-16"),
        b"<!DOCTYPE x><x/>",
    ],
)
def test_unsupported_xml_rejected(xml):
    with pytest.raises(OdtPackageError):
        text_blocks(xml)


def test_publication_failure_cleans_temporary_output(odt_factory, tmp_path, monkeypatch):
    from doc_lingo.documents.odt import writer

    path = odt_factory()
    output = tmp_path / "out.odt"

    def fail(*args):
        raise OSError("publication failed")

    monkeypatch.setattr(writer.os, "link", fail)
    with pytest.raises(OSError, match="publication failed"):
        OdtWriter(path).write(output, segments(path))
    assert not output.exists()
    assert not list(tmp_path.glob(".doc-lingo-*"))
