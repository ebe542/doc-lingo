"""Separate nonvisual language scopes and fixed leading frames from word alignment."""

from zipfile import ZipFile

import pytest

from doc_lingo import translate_document
from doc_lingo.documents.odt import OdtReader, OdtWriter, inspect_package
from doc_lingo.documents.odt.aligned import aligned_body, odt_scopes
from doc_lingo.documents.odt.inline import OdtInlineSegment
from doc_lingo.documents.odt.styles import language_only_styles
from doc_lingo.translation.alignment import AlignmentResult, TextRange
from doc_lingo.translation.model_input import prepare_model_input

OFFICE = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
STYLE = "urn:oasis:names:tc:opendocument:xmlns:style:1.0"
FO = "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
DRAW = "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"


def content(body, properties='fo:language="en" fo:country="US"', extra=""):
    return f'''<o:document-content xmlns:o="{OFFICE}" xmlns:s="{STYLE}"
      xmlns:fo="{FO}" xmlns:t="{TEXT}" xmlns:d="{DRAW}">
      <o:automatic-styles><s:style s:name="Language" s:family="text" {extra}>
      <s:text-properties {properties}/></s:style></o:automatic-styles>
      <o:body><o:text><t:p>{body}</t:p></o:text></o:body></o:document-content>'''.encode()


class Unresolved:
    def align(self, source, target):
        return AlignmentResult(source, target, unaligned=(TextRange(0, len(source)),))


def test_language_scopes_do_not_split_or_drop(odt_factory, tmp_path):
    xml = content('<t:span t:style-name="Language">Hello</t:span> world.')
    source = odt_factory(updates={"content.xml": xml})
    with OdtReader(source).iter_segments() as segments:
        segment = next(segments)
        assert isinstance(segment, OdtInlineSegment)
        assert not odt_scopes(segment)
        assert prepare_model_input(segment.translation_input()).text == "Hello world."

    class Backend:
        def translate(self, text, **kwargs):
            assert text == "Hello world."
            return "Hallo Welt."

    output = tmp_path / "out.odt"
    issues = []
    translate_document(
        OdtReader(source),
        OdtWriter(source),
        Backend(),
        output,
        source_lang="en",
        target_lang="de",
        aligner=Unresolved(),
        on_issue=issues.append,
    )
    assert not issues
    with ZipFile(output) as archive:
        assert archive.read("content.xml") == xml.replace(
            b'<t:span t:style-name="Language">Hello</t:span> world.', b"Hallo Welt."
        )


@pytest.mark.parametrize(
    "properties,extra",
    [
        ('fo:language="en" fo:font-weight="bold"', ""),
        ('fo:language="en"', 's:parent-style-name="Parent"'),
        ('fo:font-weight="normal"', ""),
    ],
)
def test_visible_or_inherited_styles_still_need_projection(odt_factory, properties, extra):
    source = odt_factory(
        updates={
            "content.xml": content(
                '<t:span t:style-name="Language">Hello</t:span> world.', properties, extra
            )
        }
    )
    assert not language_only_styles(inspect_package(source))
    with OdtReader(source).iter_segments() as segments:
        segment = next(segments)
        assert isinstance(segment, OdtInlineSegment)
        assert len(odt_scopes(segment)) == 1


def test_style_definitions_in_styles_xml_and_duplicate_names(odt_factory):
    styles = f'''<o:document-styles xmlns:o="{OFFICE}" xmlns:s="{STYLE}" xmlns:fo="{FO}">
    <o:styles><s:style s:name="Language" s:family="text"><s:text-properties fo:language="en"/>
    </s:style></o:styles></o:document-styles>'''.encode()
    source = odt_factory(updates={"content.xml": content("Hello"), "styles.xml": styles})
    assert not language_only_styles(inspect_package(source))
    xml = content("Hello").replace(b's:name="Language"', b's:name="Other"')
    source = odt_factory(updates={"content.xml": xml, "styles.xml": styles})
    assert language_only_styles(inspect_package(source)) == {"Language", "Other"}


def test_leading_frame_is_retained_without_a_marker(odt_factory, tmp_path):
    frame = '<d:frame d:name="Icon" t:anchor-type="char"><d:image/></d:frame>'
    body = frame + '<t:span t:style-name="Bold">Learning objectives:</t:span>'
    xml = content(body)
    source = odt_factory(updates={"content.xml": xml})

    class Backend:
        def translate(self, text, **kwargs):
            assert text == "Learning objectives:"
            return "Lernziele:"

    issues = []
    output = tmp_path / "out.odt"
    translate_document(
        OdtReader(source),
        OdtWriter(source),
        Backend(),
        output,
        source_lang="en",
        target_lang="de",
        aligner=Unresolved(),
        on_issue=issues.append,
    )
    with ZipFile(output) as archive:
        assert archive.read("content.xml") == xml.replace(b"Learning objectives:", b"Lernziele:")
    assert not issues


@pytest.mark.parametrize(
    "body",
    [
        "Hello <d:frame><d:image/></d:frame> world.",
        "<t:span>Hello <d:frame><d:image/></d:frame></t:span>",
        "<t:span><d:frame><d:image/></d:frame>Hello</t:span>",
    ],
)
def test_interior_or_wrapped_frames_still_use_markers(odt_factory, body):
    source = odt_factory(updates={"content.xml": content(body)})
    with OdtReader(source).iter_segments() as segments:
        segment = next(segments)
        assert isinstance(segment, OdtInlineSegment)
        prefix, prepared_body = aligned_body(segment)
        assert prefix == ""
        assert prepare_model_input(prepared_body.translation_input()).markers


def test_language_metadata_round_trip_remains_byte_identical(odt_factory, tmp_path):
    source = odt_factory(
        updates={"content.xml": content('<t:span t:style-name="Language">Hello</t:span>')}
    )
    output = tmp_path / "out.odt"
    with OdtReader(source).iter_segments() as segments:
        OdtWriter(source).write(output, segments)
    with ZipFile(source) as original, ZipFile(output) as translated:
        for name in original.namelist():
            assert original.read(name) == translated.read(name)


def test_multiple_leading_frames_keep_order_and_body_coordinates(odt_factory):
    prefix = '<d:frame d:name="one"/> <d:frame d:name="two"/>'
    source = odt_factory(
        updates={"content.xml": content(prefix + '<t:span t:style-name="Language">Hello</t:span>')}
    )
    with OdtReader(source).iter_segments() as segments:
        segment = next(segments)
        assert isinstance(segment, OdtInlineSegment)
        leading, body = aligned_body(segment)
        assert leading == prefix
        assert prepare_model_input(body.translation_input()).text == "Hello"
        assert body.language_ranges == {0}
        assert body.frame_spans == ()


@pytest.mark.parametrize(
    "prefix",
    [
        "<t:soft-page-break/>",
        "<t:soft-page-break /> <t:soft-page-break/>",
        '<d:frame d:name="Icon"/><t:soft-page-break/>',
        '<t:soft-page-break/><d:frame d:name="Icon"/>',
    ],
)
@pytest.mark.parametrize("partial", [False, True])
def test_leading_soft_break_keeps_only_complete_style(odt_factory, tmp_path, prefix, partial):
    body = (
        '<t:span t:style-name="Bold">Hello</t:span> world.'
        if partial
        else '<t:span t:style-name="Bold">Hello world.</t:span>'
    )
    xml = content(prefix + body)
    source = odt_factory(updates={"content.xml": xml})

    class Backend:
        def translate(self, text, **kwargs):
            assert text == "Hello world."
            return "Hallo Welt."

    issues = []
    output = tmp_path / "out.odt"
    translate_document(
        OdtReader(source),
        OdtWriter(source),
        Backend(),
        output,
        source_lang="en",
        target_lang="de",
        aligner=Unresolved(),
        on_issue=issues.append,
    )
    translated = "Hallo Welt." if partial else '<t:span t:style-name="Bold">Hallo Welt.</t:span>'
    with ZipFile(output) as archive:
        assert archive.read("content.xml") == xml.replace(body.encode(), translated.encode())
    assert len(issues) == int(partial)
    if partial:
        assert issues[0].action == "formatting_dropped"
        assert "unresolved_source" in issues[0].reason


@pytest.mark.parametrize(
    "body",
    [
        "Hello<t:soft-page-break/> world.",
        "<t:span><t:soft-page-break/>Hello</t:span>",
        "<t:line-break/><t:soft-page-break/>Hello",
        "<t:page-number>1</t:page-number><t:soft-page-break/>Hello",
    ],
)
def test_nonleading_or_wrapped_soft_break_is_still_protected(odt_factory, body):
    source = odt_factory(updates={"content.xml": content(body)})
    with OdtReader(source).iter_segments() as segments:
        segment = next(segments)
        prefix, translated_body = aligned_body(segment)
        assert prefix == ""
        assert prepare_model_input(translated_body.translation_input()).markers


def test_whitespace_style_is_omitted_without_losing_text(odt_factory, tmp_path):
    body = 'Hello<t:span t:style-name="Bold"> </t:span>world.'
    xml = content(body)
    source = odt_factory(updates={"content.xml": xml})

    class Backend:
        def translate(self, text, **kwargs):
            assert text == "Hello world."
            return "Hallo Welt."

    issues = []
    output = tmp_path / "out.odt"
    translate_document(
        OdtReader(source),
        OdtWriter(source),
        Backend(),
        output,
        source_lang="en",
        target_lang="de",
        aligner=Unresolved(),
        on_issue=issues.append,
    )
    assert issues == []
    with ZipFile(output) as archive:
        assert archive.read("content.xml") == xml.replace(body.encode(), b"Hallo Welt.")


@pytest.mark.parametrize("inner", [".", "Hello", "<t:s/>", "<t:tab/>"])
def test_punctuation_and_explicit_whitespace_scopes_are_not_silenced(odt_factory, inner):
    source = odt_factory(
        updates={"content.xml": content(f'<t:span t:style-name="Bold">{inner}</t:span> world.')}
    )
    with OdtReader(source).iter_segments() as segments:
        assert len(odt_scopes(next(segments))) == 1


def test_whitespace_link_still_requires_projection(odt_factory):
    source = odt_factory(updates={"content.xml": content("Hello<t:a> </t:a>world.")})
    with OdtReader(source).iter_segments() as segments:
        scopes = odt_scopes(next(segments))
        assert len(scopes) == 1
        assert scopes[0].link_target is not None
