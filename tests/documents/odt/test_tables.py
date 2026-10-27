"""Table text translation preserves cell structure and opaque cell values."""

from zipfile import ZipFile

import pytest

from doc_lingo import translate_document
from doc_lingo.documents.odt import OdtReader, OdtWriter
from doc_lingo.documents.odt.diagnostics import skipped_text_issues
from doc_lingo.translation.alignment import AlignmentResult, TextRange


def document(body):
    return f"""<o:document-content
      xmlns:o="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
      xmlns:t="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
      xmlns:b="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
      xmlns:d="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0">
      <o:body><o:text>{body}</o:text></o:body></o:document-content>""".encode()


def test_nested_tables_merged_cells_and_multiple_paragraphs(odt_factory, tmp_path):
    xml = document("""<b:table b:name="Outer"><b:table-column b:number-columns-repeated="2"/>
      <b:table-header-rows><b:table-row><b:table-cell b:number-columns-spanned="2"
      b:style-name="HeadingCell"><t:h t:outline-level="2">Header</t:h></b:table-cell>
      <b:covered-table-cell/></b:table-row></b:table-header-rows>
      <b:table-row-group><b:table-rows><b:table-row b:number-rows-repeated="2">
      <b:table-cell o:value-type="string" b:number-rows-spanned="2"><t:p>First</t:p>
      <t:p>Second</t:p><b:table b:name="Inner"><b:table-row><b:table-cell>
      <t:p>Nested</t:p></b:table-cell></b:table-row></b:table>
      <t:list><t:list-item><t:p>Item</t:p></t:list-item></t:list></b:table-cell>
      <b:table-cell b:number-columns-repeated="3"><t:p>Last</t:p><t:p/></b:table-cell>
      </b:table-row></b:table-rows></b:table-row-group></b:table>""")
    source = odt_factory(updates={"content.xml": xml})
    calls = []
    with OdtReader(source).iter_segments() as values:
        segments = list(values)
    assert [(s.id, s.text, s.type) for s in segments] == [
        ("1", "Header", "heading"),
        ("2", "First", "paragraph"),
        ("3", "Second", "paragraph"),
        ("4", "Nested", "paragraph"),
        ("5", "Item", "list_item"),
        ("6", "Last", "paragraph"),
    ]

    class Backend:
        def translate(self, text, **kwargs):
            calls.append(text)
            return text.upper()

    output = tmp_path / "out.odt"
    translate_document(
        OdtReader(source), OdtWriter(source), Backend(), output, source_lang="en", target_lang="de"
    )
    assert calls == [s.text for s in segments]
    expected = xml
    for text in calls:
        expected = expected.replace(f">{text}<".encode(), f">{text.upper()}<".encode())
    with ZipFile(source) as original, ZipFile(output) as translated:
        assert translated.read("content.xml") == expected
        for name in original.namelist():
            if name != "content.xml":
                assert translated.read(name) == original.read(name)
    assert not skipped_text_issues(source)


@pytest.mark.parametrize(
    "attributes",
    [
        'b:formula="of:=1+1"',
        'o:value-type="float" o:value="2"',
        'o:value-type="date" o:date-value="2026-10-17"',
        'o:value-type="string" o:string-value="Keep"',
        'o:value="2"',
    ],
)
def test_stored_values_remain_unchanged_and_reported(odt_factory, tmp_path, attributes):
    xml = document(f"""<b:table><b:table-row><b:table-cell {attributes}>
      <t:p>Keep</t:p></b:table-cell><b:table-cell><t:p>Translate</t:p></b:table-cell>
      </b:table-row></b:table>""")
    source = odt_factory(updates={"content.xml": xml})
    reader = OdtReader(source)
    with reader.iter_segments() as values:
        segments = list(values)
    assert [(s.id, s.text) for s in segments] == [("2", "Translate")]
    assert reader.skipped_blocks[0].reason == "unsupported_cell_value"
    issues = skipped_text_issues(source)
    assert len(issues) == 1 and issues[0].original == "Keep"
    output = tmp_path / "out.odt"
    OdtWriter(source).write(output, segments)
    with ZipFile(output) as archive:
        assert archive.read("content.xml") == xml


@pytest.mark.parametrize(
    "prefix,suffix",
    [
        ("<d:g><d:frame><d:text-box>", "</d:text-box></d:frame></d:g>"),
        ('<t:section t:name="UnknownContext">', "</t:section>"),
    ],
)
def test_table_does_not_enable_unsupported_outer_containers(odt_factory, prefix, suffix):
    xml = document(
        prefix + "<b:table><b:table-row><b:table-cell><t:p>Keep</t:p>"
        "</b:table-cell></b:table-row></b:table>" + suffix
    )
    source = odt_factory(updates={"content.xml": xml})
    with OdtReader(source).iter_segments() as values:
        assert list(values) == []
    assert skipped_text_issues(source)[0].original == "Keep"


def test_cell_uses_existing_alignment_path(odt_factory, tmp_path):
    xml = document(
        "<b:table><b:table-row><b:table-cell><t:p>"
        '<t:span t:style-name="Bold">Hello world.</t:span>'
        "</t:p></b:table-cell></b:table-row></b:table>"
    )
    source = odt_factory(updates={"content.xml": xml})

    class Backend:
        def translate(self, text, **kwargs):
            assert text == "Hello world."
            return "Hallo Welt."

    class Aligner:
        def align(self, source, target):
            return AlignmentResult(source, target, unaligned=(TextRange(0, len(source)),))

    output = tmp_path / "out.odt"
    translate_document(
        OdtReader(source),
        OdtWriter(source),
        Backend(),
        output,
        source_lang="en",
        target_lang="de",
        aligner=Aligner(),
    )
    with ZipFile(output) as archive:
        assert archive.read("content.xml") == xml.replace(b"Hello world.", b"Hallo Welt.")
