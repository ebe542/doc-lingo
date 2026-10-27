"""Header/footer edits share protection rules but use part-local byte offsets."""

from dataclasses import replace
from zipfile import ZipFile

import pytest

from doc_lingo import translate_document
from doc_lingo.documents.errors import SegmentMismatchError
from doc_lingo.documents.odt import OdtReader, OdtWriter
from doc_lingo.documents.odt.diagnostics import skipped_text_issues
from doc_lingo.translation.alignment import AlignmentLink, AlignmentResult, TextRange
from scripts.evaluate_odt import evaluate_odt

REGIONS = ("header", "header-left", "header-first", "footer", "footer-left", "footer-first")


def styles(body):
    return f"""<o:document-styles
      xmlns:o="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
      xmlns:t="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
      xmlns:s="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
      xmlns:d="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
      xmlns:x="http://www.w3.org/1999/xlink">
      <o:styles><s:style s:name="Keep" s:family="paragraph"/></o:styles>
      <o:automatic-styles><s:page-layout s:name="Layout"/></o:automatic-styles>
      <o:master-styles>{body}</o:master-styles></o:document-styles>""".encode()


def master(body, name="Standard"):
    return f'<s:master-page s:name="{name}" s:page-layout-name="Layout">{body}</s:master-page>'


def segments(source):
    with OdtReader(source).iter_segments() as values:
        return list(values)


@pytest.mark.parametrize("region", REGIONS)
def test_regions_patch_only_prose_and_keep_parts_distinct(odt_factory, tmp_path, region):
    xml = styles(
        master(f'<s:{region}><t:p t:style-name="Keep">Header &amp; footer</t:p></s:{region}>')
    )
    source = odt_factory(updates={"styles.xml": xml})
    values = segments(source)
    assert values[0].id == "1"
    assert values[-1].id == "styles.xml:1"
    assert len({s.id for s in values}) == len(values)
    output = tmp_path / "out.odt"
    values[-1] = replace(values[-1], text="Kopf & Fuß")
    OdtWriter(source).write(output, values)
    with ZipFile(source) as original, ZipFile(output) as translated:
        assert translated.namelist() == original.namelist()
        for name in original.namelist():
            expected = original.read(name)
            if name == "styles.xml":
                expected = xml.replace(b"Header &amp; footer", "Kopf &amp; Fuß".encode())
            assert translated.read(name) == expected
    assert not skipped_text_issues(source)


@pytest.mark.parametrize("aligned", [False, True])
def test_fields_images_and_nested_boxes_are_preserved(odt_factory, tmp_path, aligned):
    xml = styles(
        master("""<s:header><t:p>Header <t:page-number t:select-page="current">1</t:page-number>
      / <t:page-count>2</t:page-count><d:frame d:name="Logo">
      <d:image x:href="Pictures/pixel.png"/></d:frame></t:p>
      <t:p>Outer <d:frame><d:text-box><t:p>Caption</t:p></d:text-box></d:frame></t:p>
      </s:header><s:footer><t:p>Footer</t:p></s:footer>""")
    )
    source = odt_factory(updates={"styles.xml": xml})
    calls = []

    class Backend:
        def translate(self, text, **kwargs):
            calls.append(text)
            for old, new in (("Header", "Kopf"), ("Footer", "Fuß"), ("Caption", "Bildtext")):
                text = text.replace(old, new)
            return text

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
        aligner=Aligner() if aligned else None,
    )
    assert sum("Caption" in call for call in calls) == 1
    assert all("Logo" not in call and "<" not in call for call in calls)
    with ZipFile(output) as archive:
        expected = xml.replace(b"Header", b"Kopf").replace(b"Footer", "Fuß".encode())
        assert archive.read("styles.xml") == expected.replace(b"Caption", b"Bildtext")


def test_round_trip_and_unsupported_regions_remain_exact(odt_factory, tmp_path):
    xml = styles(
        master("""<s:header><t:p>H&#101;ader</t:p><t:p/>
      <t:p><t:page-number>1</t:page-number></t:p>
      <t:p t:style-name="Preformatted_20_Text">Keep code</t:p>
      <t:section><t:p>Section</t:p></t:section>
      <t:p>Unknown <t:unknown>field</t:unknown></t:p></s:header>
      <s:unknown><t:p>Outside</t:p></s:unknown>""")
    )
    source = odt_factory(updates={"styles.xml": xml})
    output = tmp_path / "out.odt"
    OdtWriter(source).write(output, segments(source))
    with ZipFile(source) as original, ZipFile(output) as translated:
        assert all(original.read(n) == translated.read(n) for n in original.namelist())
    issues = skipped_text_issues(source)
    assert [(i.segment_id, i.original) for i in issues] == [
        ("styles.xml:5", "Section"),
        ("styles.xml:6", "Unknown field"),
        ("styles.xml:7", "Outside"),
    ]


@pytest.mark.parametrize("suffix", ["", " of this document"])
def test_field_protection_and_recovery_continue_to_footer(odt_factory, tmp_path, suffix):
    xml = styles(
        master(f"""<s:header><t:p>Page <t:page-number>1</t:page-number>{suffix}</t:p></s:header>
      <s:footer><t:p>Footer</t:p></s:footer>""")
    )
    source = odt_factory(updates={"styles.xml": xml})
    issues = []

    class Backend:
        def translate(self, text, **kwargs):
            if "Page" in text:
                # A trailing field bypasses the backend; an interior field becomes a marker.
                assert ("DLM" in text) == bool(suffix)
                return "Seite "
            return "Fuß" if text == "Footer" else text

    output = tmp_path / "out.odt"
    translate_document(
        OdtReader(source),
        OdtWriter(source),
        Backend(),
        output,
        source_lang="en",
        target_lang="de",
        on_issue=issues.append,
    )
    expected_issues = [("styles.xml:1", "retained_original")] if suffix else []
    assert [(i.segment_id, i.action) for i in issues] == expected_issues
    if suffix:
        assert issues[0].diagnostics is not None
        assert any(
            error.startswith("missing_marker:") for error in issues[0].diagnostics.validation_errors
        )
    expected = xml.replace(b"Footer", "Fuß".encode())
    if not suffix:
        expected = expected.replace(b">Page ", b">Seite ")
    with ZipFile(output) as archive:
        assert archive.read("styles.xml") == expected


def test_multiple_master_pages_count_stored_occurrences_in_review(odt_factory, tmp_path):
    xml = styles(
        "".join(master("<s:header><t:p>Header</t:p></s:header>", name) for name in ("A", "B"))
    )
    source = odt_factory(updates={"styles.xml": xml})

    class Backend:
        def translate(self, text, **kwargs):
            return "Kopf" if text == "Header" else text

    report = evaluate_odt(source, tmp_path / "review", Backend(), None, metadata={})
    assert report["report_version"] == 2
    assert report["processed_segments"] == report["eligible_segments"] == 8
    assert [r["segment_id"] for r in report["peripheral_text"]] == ["styles.xml:1", "styles.xml:2"]
    assert all(r["status"] == "eligible" for r in report["peripheral_text"])
    assert "styles.xml" not in report["unchanged_members"]
    with ZipFile(tmp_path / "review/translated.de.odt") as archive:
        assert archive.read("styles.xml") == xml.replace(b"Header", b"Kopf")


def test_wrong_part_id_is_rejected_before_publication(odt_factory, tmp_path):
    source = odt_factory(
        updates={"styles.xml": styles(master("<s:header><t:p>Header</t:p></s:header>"))}
    )
    values = segments(source)
    values[-1] = replace(values[-1], id="1")
    output = tmp_path / "out.odt"
    with pytest.raises(SegmentMismatchError):
        OdtWriter(source).write(output, values)
    assert not output.exists()


@pytest.mark.parametrize("aligned", [False, True])
def test_header_style_and_link_wrappers_keep_attributes(odt_factory, tmp_path, aligned):
    xml = styles(
        master(
            '<s:header><t:p><t:a x:href="https://example.org/Header">'
            '<t:span t:style-name="Keep">Header</t:span></t:a></t:p></s:header>'
        )
    )
    source = odt_factory(updates={"styles.xml": xml})

    class Backend:
        def translate(self, text, **kwargs):
            assert "example.org" not in text and "Keep" not in text
            return text.replace("Header", "Kopf")

    class Aligner:
        def align(self, source, target):
            return AlignmentResult(
                source,
                target,
                (AlignmentLink((TextRange(0, len(source)),), (TextRange(0, len(target)),)),),
            )

    output = tmp_path / "out.odt"
    translate_document(
        OdtReader(source),
        OdtWriter(source),
        Backend(),
        output,
        source_lang="en",
        target_lang="de",
        aligner=Aligner() if aligned else None,
    )
    with ZipFile(output) as archive:
        assert archive.read("styles.xml") == xml.replace(b">Header<", b">Kopf<")


@pytest.mark.parametrize("aligned", [False, True])
@pytest.mark.parametrize("separator", ["/ ", " – ", "<t:s/>/ ", "&#160;|&#160;"])
def test_field_only_footer_bypasses_backend_and_keeps_xml(
    odt_factory, tmp_path, aligned, separator
):
    xml = styles(
        master(
            '<s:footer><t:p><t:span t:style-name="Keep">'
            '<t:page-number t:select-page="current">6</t:page-number>'
            f"{separator}<t:page-count>6</t:page-count>"
            "</t:span></t:p></s:footer>"
        )
    )
    body = (
        b'<o:document-content xmlns:o="urn:oasis:names:tc:opendocument:xmlns:office:1.0">'
        b"<o:body><o:text/></o:body></o:document-content>"
    )
    source = odt_factory(updates={"styles.xml": xml, "content.xml": body})
    calls = []
    issues = []

    class Backend:
        def translate(self, text, **kwargs):
            calls.append(text)
            return text

    class Aligner:
        def align(self, source, target):
            return AlignmentResult(source, target, unaligned=(TextRange(0, len(source)),))

    reader = OdtReader(source)
    output = tmp_path / "out.odt"
    translate_document(
        reader,
        OdtWriter(source),
        Backend(),
        output,
        source_lang="en",
        target_lang="de",
        on_issue=issues.append,
        aligner=Aligner() if aligned else None,
    )
    assert calls == []
    assert not any(i.segment_id.startswith("styles.xml:") for i in issues)
    assert [(b.segment.id, b.reason) for b in reader.skipped_blocks if b.part == "styles.xml"] == [
        ("styles.xml:1", "protected_only")
    ]
    assert not skipped_text_issues(source)
    with ZipFile(output) as archive:
        assert archive.read("styles.xml") == xml


@pytest.mark.parametrize("prose", ["Page ", " von ", "第", "6", " / next"])
def test_field_with_prose_or_literal_number_remains_eligible(odt_factory, prose):
    xml = styles(master(f"<s:footer><t:p>{prose}<t:page-number>1</t:page-number></t:p></s:footer>"))
    source = odt_factory(updates={"styles.xml": xml})
    assert segments(source)[-1].id == "styles.xml:1"


def test_punctuation_without_field_remains_eligible(odt_factory):
    xml = styles(master("<s:footer><t:p><t:span>/</t:span></t:p></s:footer>"))
    source = odt_factory(updates={"styles.xml": xml})
    assert segments(source)[-1].id == "styles.xml:1"
