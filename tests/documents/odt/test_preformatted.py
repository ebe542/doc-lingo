"""Explicit preformatted-style protection without guessing code from prose."""

from zipfile import ZipFile

import pytest

from doc_lingo import translate_document
from doc_lingo.documents.odt import OdtReader, OdtWriter, inspect_package
from doc_lingo.documents.odt.diagnostics import skipped_text_issues
from doc_lingo.documents.odt.styles import preformatted_styles
from scripts.evaluate_odt import inventory

OFFICE = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
STYLE = "urn:oasis:names:tc:opendocument:xmlns:style:1.0"
TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
TABLE = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"


def document(body, definitions=""):
    return f'''<o:document-content xmlns:o="{OFFICE}" xmlns:s="{STYLE}"
      xmlns:t="{TEXT}" xmlns:b="{TABLE}"><o:automatic-styles>{definitions}</o:automatic-styles>
      <o:body><o:text>{body}</o:text></o:body></o:document-content>'''.encode()


@pytest.mark.parametrize("in_table", [False, True])
def test_code_never_reaches_backend_or_aligner(odt_factory, tmp_path, in_table):
    definitions = """<s:style s:name="P29" s:family="paragraph"
      s:parent-style-name="CodeBase"/><s:style s:name="P30" s:family="paragraph"
      s:parent-style-name="P29"/>"""
    styles = f'''<o:document-styles xmlns:o="{OFFICE}" xmlns:s="{STYLE}">
      <o:styles><s:style s:name="CodeBase" s:family="paragraph"
      s:parent-style-name="Preformatted_20_Text"/></o:styles></o:document-styles>'''.encode()
    body = """<t:p t:style-name="P29">for number in numbers:</t:p>
      <t:p t:style-name="P30"><t:s t:c="2"/>is_prime = True</t:p>
      <t:p t:style-name="Preformatted_20_Text"># Keep this comment.</t:p>
      <t:p>Hello</t:p>"""
    if in_table:
        body = (
            "<b:table><b:table-row><b:table-cell>"
            + body
            + "</b:table-cell></b:table-row></b:table>"
        )
    xml = document(body, definitions)
    source = odt_factory(updates={"content.xml": xml, "styles.xml": styles})
    calls = []

    class Backend:
        def translate(self, text, **kwargs):
            calls.append(text)
            assert text == "Hello"
            return "Hallo"

    class NoAligner:
        def align(self, source, target):
            pytest.fail("Only the ordinary plain-text paragraph is translated")

    output = tmp_path / "out.odt"
    reader = OdtReader(source)
    translate_document(
        reader,
        OdtWriter(source),
        Backend(),
        output,
        source_lang="en",
        target_lang="de",
        aligner=NoAligner(),
    )
    assert calls == ["Hello"]
    assert [b.reason for b in reader.skipped_blocks] == ["protected_preformatted"] * 3
    assert not skipped_text_issues(source)
    rows, _ = inventory(inspect_package(source))
    assert [r["reason"] for r in rows] == ["protected_preformatted"] * 3 + [None]
    with ZipFile(source) as original, ZipFile(output) as translated:
        assert translated.read("content.xml") == xml.replace(b">Hello<", b">Hallo<")
        for name in original.namelist():
            if name != "content.xml":
                assert translated.read(name) == original.read(name)


def test_cycles_missing_parents_and_duplicate_definitions(odt_factory):
    definitions = """<s:style s:name="A" s:family="paragraph" s:parent-style-name="B"/>
      <s:style s:name="B" s:family="paragraph" s:parent-style-name="A"/>
      <s:style s:name="Unknown" s:family="paragraph" s:parent-style-name="Missing"/>
      <s:style s:name="Duplicate" s:family="paragraph" s:parent-style-name="A"/>
      <s:style s:name="Duplicate" s:family="paragraph" s:parent-style-name="Preformatted_20_Text"/>
      <s:style s:name="Display" s:family="paragraph" s:display-name="Preformatted Text"/>
      <s:style s:name="Inline" s:family="text" s:parent-style-name="Preformatted_20_Text"/>"""
    source = odt_factory(updates={"content.xml": document("<t:p>Hello</t:p>", definitions)})
    protected = preformatted_styles(inspect_package(source))
    assert {"Duplicate", "Display"} <= protected
    assert not {"A", "B", "Unknown", "Inline"} & protected


def test_ordinary_prose_is_not_detected_as_code(odt_factory):
    source = odt_factory(
        updates={
            "content.xml": document(
                "<t:p>True and False are boolean values.</t:p><t:p>for number in numbers:</t:p>"
            )
        }
    )
    with OdtReader(source).iter_segments() as values:
        assert [s.text for s in values] == [
            "True and False are boolean values.",
            "for number in numbers:",
        ]


def test_missing_styles_part_still_protects_explicit_style(odt_factory):
    source = odt_factory(
        updates={
            "content.xml": document('<t:p t:style-name="Preformatted_20_Text">print(number)</t:p>')
        },
        omit=("styles.xml",),
    )
    # The package manifest must not declare an omitted member.
    with ZipFile(source) as archive:
        manifest = archive.read("META-INF/manifest.xml").decode()
    manifest = "\n".join(line for line in manifest.splitlines() if '"styles.xml"' not in line)
    source = odt_factory(
        updates={
            "content.xml": document('<t:p t:style-name="Preformatted_20_Text">print(number)</t:p>'),
            "META-INF/manifest.xml": manifest.encode(),
        },
        omit=("styles.xml",),
    )
    with OdtReader(source).iter_segments() as values:
        assert list(values) == []
