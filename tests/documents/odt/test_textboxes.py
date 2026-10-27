"""Nested frame edits preserve outer XML while translating each paragraph once."""

from zipfile import ZipFile

import pytest

from doc_lingo import translate_document
from doc_lingo.documents.models import TextSegment
from doc_lingo.documents.odt import OdtPackageError, OdtReader, OdtWriter
from doc_lingo.documents.odt.blocks import OdtBlock
from doc_lingo.documents.odt.patches import compose_blocks
from doc_lingo.translation.alignment import AlignmentResult, TextRange


def document(body):
    return f"""<o:document-content
    xmlns:o="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
    xmlns:t="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
    xmlns:d="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
    xmlns:b="urn:oasis:names:tc:opendocument:xmlns:table:1.0">
    <o:body><o:text>{body}</o:text></o:body></o:document-content>""".encode()


@pytest.mark.parametrize("aligned", [False, True])
def test_parent_and_nested_textboxes_are_composed_once(odt_factory, tmp_path, aligned):
    xml = document("""<t:p>Outer <d:frame d:name="Box1" t:anchor-type="char">
      <d:text-box><t:p>First</t:p><t:p>Second <d:frame d:name="Box2">
      <d:text-box><t:p>Deep</t:p></d:text-box></d:frame> end</t:p>
      <t:p>Figure <t:sequence t:name="Illustration" t:ref-name="ref1">1</t:sequence>: Caption</t:p>
      <t:p/></d:text-box></d:frame> tail</t:p>""")
    source = odt_factory(updates={"content.xml": xml})
    calls = []
    words = {
        "Outer": "Außen",
        "First": "Erster",
        "Second": "Zweiter",
        "Deep": "Tief",
        "end": "Ende",
        "Figure": "Abbildung",
        "Caption": "Bildtext",
        "tail": "Rest",
    }

    class Backend:
        def translate(self, text, **kwargs):
            calls.append(text)
            assert "<" not in text and "Illustration" not in text and "Box" not in text
            for old, new in words.items():
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
    assert len(calls) == 5
    assert all(
        sum(word in call for call in calls) == 1
        for word in ("Outer", "First", "Second", "Deep", "Caption")
    )
    # Spell out translated prose independently; a global replacement of "end"
    # would also corrupt the unchanged "opendocument" namespace addresses.
    expected = document(
        """<t:p>Außen <d:frame d:name="Box1" t:anchor-type="char">
      <d:text-box><t:p>Erster</t:p><t:p>Zweiter <d:frame d:name="Box2">
      <d:text-box><t:p>Tief</t:p></d:text-box></d:frame> Ende</t:p>
      <t:p>Abbildung """
        + '<t:sequence t:name="Illustration" t:ref-name="ref1">'
        + """1</t:sequence>: Bildtext</t:p>
      <t:p/></d:text-box></d:frame> Rest</t:p>"""
    )
    with ZipFile(source) as original, ZipFile(output) as translated:
        assert translated.read("content.xml") == expected
        for name in original.namelist():
            if name != "content.xml":
                assert original.read(name) == translated.read(name)


def test_standalone_and_frame_only_parents_support_lists_and_tables(odt_factory, tmp_path):
    xml = document("""<d:frame><d:text-box><t:p>Standalone</t:p></d:text-box></d:frame>
    <t:p><t:span><d:frame><d:text-box><t:list><t:list-item><t:p>Item</t:p>
    </t:list-item></t:list><b:table><b:table-row><b:table-cell><t:p>Cell</t:p>
    </b:table-cell></b:table-row></b:table></d:text-box></d:frame></t:span></t:p>""")
    source = odt_factory(updates={"content.xml": xml})
    with OdtReader(source).iter_segments() as values:
        segments = list(values)
    assert [(s.text, s.type) for s in segments] == [
        ("Standalone", "paragraph"),
        ("Item", "list_item"),
        ("Cell", "paragraph"),
    ]
    output = tmp_path / "out.odt"
    OdtWriter(source).write(output, segments)
    with ZipFile(output) as archive:
        assert archive.read("content.xml") == xml


def test_parent_recovery_does_not_discard_child_translation(odt_factory, tmp_path):
    xml = document(
        "<t:p>Before <d:frame><d:text-box><t:p>Child</t:p></d:text-box></d:frame> after</t:p>"
    )
    source = odt_factory(updates={"content.xml": xml})
    issues = []

    class Backend:
        def translate(self, text, **kwargs):
            return "Kind" if text == "Child" else "Marker lost"

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
    assert any(i.action == "retained_original" and i.segment_id == "1" for i in issues)
    with ZipFile(output) as archive:
        assert archive.read("content.xml") == xml.replace(b">Child<", b">Kind<")


def test_protected_parent_keeps_nested_textbox_untouched(odt_factory):
    xml = document(
        '<t:p t:style-name="Preformatted_20_Text">Code <d:frame>'
        "<d:text-box><t:p>Keep</t:p></d:text-box></d:frame></t:p>"
    )
    source = odt_factory(updates={"content.xml": xml})
    with OdtReader(source).iter_segments() as values:
        assert list(values) == []


def test_patch_composition_rejects_missing_frame_evidence():
    content = b"A<frame>child</frame>Z"
    parent = OdtBlock(TextSegment("1", ""), 0, len(content), frames=((1, len(content) - 1),))
    child = OdtBlock(TextSegment("2", ""), 8, 13)
    with pytest.raises(OdtPackageError, match="parent frame changed"):
        compose_blocks(content, (parent, child), {"1": b"changed", "2": b"translated"})


def test_nested_round_trip_and_outer_list_type(odt_factory, tmp_path):
    xml = document(
        "<t:list><t:list-item><t:p>Outer <d:frame><d:text-box>"
        "<t:p>Inner</t:p></d:text-box></d:frame></t:p></t:list-item></t:list>"
    )
    source = odt_factory(updates={"content.xml": xml})
    with OdtReader(source).iter_segments() as values:
        segments = list(values)
    assert [s.type for s in segments] == ["list_item", "paragraph"]
    output = tmp_path / "out.odt"
    OdtWriter(source).write(output, segments)
    with ZipFile(output) as archive:
        assert archive.read("content.xml") == xml


def test_caption_field_loss_keeps_caption_and_continues(odt_factory, tmp_path):
    xml = document(
        '<d:frame><d:text-box><t:p>Figure <t:sequence t:name="Figure">1'
        "</t:sequence>: Caption</t:p><t:p>Next</t:p></d:text-box></d:frame>"
    )
    source = odt_factory(updates={"content.xml": xml})
    issues = []

    class Backend:
        def translate(self, text, **kwargs):
            return "Weiter" if text == "Next" else "Abbildung: Bildtext"

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
    assert any(i.segment_id == "1" and i.action == "retained_original" for i in issues)
    with ZipFile(output) as archive:
        assert archive.read("content.xml") == xml.replace(b">Next<", b">Weiter<")
