"""Deterministic ODT projection without model downloads or GPU access."""

import re
from dataclasses import replace
from zipfile import ZipFile

import pytest

from doc_lingo import translate_document
from doc_lingo.documents.odt import OdtPackageError, OdtReader, OdtWriter
from doc_lingo.documents.odt.aligned import (
    AlignedOdtSegment,
    odt_scopes,
    render_aligned,
    supports_projection,
)
from doc_lingo.documents.odt.blocks import text_blocks
from doc_lingo.documents.odt.inline import OdtInlineSegment
from doc_lingo.translation.alignment import (
    AlignmentError,
    AlignmentLink,
    AlignmentResult,
    TextRange,
)
from doc_lingo.translation.formatting import FormattingProjection, ProjectedFormatting
from doc_lingo.translation.formatting_bridge import RestoredFormatting
from doc_lingo.translation.model_input import prepare_model_input


def document(body):
    return f"""<o:document-content
 xmlns:o="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:t="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
 xmlns:x="http://www.w3.org/1999/xlink"><o:body><o:text>
 <t:p>{body}</t:p></o:text></o:body></o:document-content>""".encode()


def inline(body):
    segment = text_blocks(document(body))[0].segment
    assert isinstance(segment, OdtInlineSegment)
    return segment


class Backend:
    def translate(self, text, **kwargs):
        assert text == "Turn off device."
        return "Schalte Gerät aus."


class Aligner:
    def align(self, source, target):
        words = {"Turn": "Schalte", "off": "aus", "device": "Gerät", ".": "."}
        links = []
        for match in re.finditer(r"\w+|[^\w\s]", source):
            word = words[match.group()]
            start = target.index(word)
            links.append(
                AlignmentLink(
                    (TextRange(match.start(), match.end()),), (TextRange(start, start + len(word)),)
                )
            )
        return AlignmentResult(source, target, tuple(links))


@pytest.mark.parametrize(
    "opening,closing,expected,action",
    [
        (
            '<t:span t:style-name="Bold">',
            "</t:span>",
            '<t:span t:style-name="Bold">Schalte</t:span> Gerät '
            '<t:span t:style-name="Bold">aus</t:span>.',
            "formatting_split",
        ),
        (
            '<t:a x:href="https://example.org/?a=1&amp;b=2">',
            "</t:a>",
            '<t:a x:href="https://example.org/?a=1&amp;b=2">Schalte Gerät aus</t:a>.',
            "formatting_expanded",
        ),
    ],
)
def test_split_style_and_expanded_link(odt_factory, tmp_path, opening, closing, expected, action):
    body = opening + "Turn off" + closing + " device."
    source = odt_factory(updates={"content.xml": document(body)})
    output = tmp_path / "out.odt"
    issues = []
    translate_document(
        OdtReader(source),
        OdtWriter(source),
        Backend(),
        output,
        source_lang="en",
        target_lang="de",
        aligner=Aligner(),
        on_issue=issues.append,
    )
    with ZipFile(source) as original, ZipFile(output) as translated:
        assert translated.read("content.xml") == document(expected)
        for name in original.namelist():
            if name != "content.xml":
                assert translated.read(name) == original.read(name)
    assert any(issue.action == action for issue in issues)


def test_decoded_layout_keeps_unicode_coordinates_and_protected_content():
    source = inline(
        'caf&#233; <t:span t:style-name="Bold">&amp; <t:a x:href="url">tea</t:a>'
        "</t:span> <t:page-number>1</t:page-number>"
    )
    prepared = prepare_model_input(source.translation_input())
    assert prepared.text == "café & tea " + prepared.markers[0].token
    assert len(prepared.markers) == 1
    assert len(source.ranges) == 2
    assert len(odt_scopes(source)) == 2
    assert odt_scopes(source)[1].link_target == '<t:a x:href="url">'


def test_nested_styles_render_and_escape_prose():
    source = inline(
        '<t:span t:style-name="Outer"><t:span t:style-name="Inner">Hi</t:span></t:span>'
    )
    scopes = odt_scopes(source)
    restored = RestoredFormatting(
        "A & <B>",
        FormattingProjection(
            tuple(ProjectedFormatting(scope, (TextRange(0, 7),)) for scope in scopes), ()
        ),
    )
    rendered, issues = render_aligned(source, restored)
    assert rendered == (
        '<t:span t:style-name="Outer"><t:span t:style-name="Inner">'
        "A &amp; &lt;B&gt;</t:span></t:span>"
    )
    assert not issues


def test_unresolved_partial_scope_is_dropped(odt_factory, tmp_path):
    class FailedAligner:
        def align(self, source, target):
            raise AlignmentError("no correspondence")

    source = odt_factory(updates={"content.xml": document("<t:span>Turn off</t:span> device.")})
    output = tmp_path / "out.odt"
    issues = []
    translate_document(
        OdtReader(source),
        OdtWriter(source),
        Backend(),
        output,
        source_lang="en",
        target_lang="de",
        aligner=FailedAligner(),
        on_issue=issues.append,
    )
    with ZipFile(output) as archive:
        assert archive.read("content.xml") == document("Schalte Gerät aus.")
    assert any(issue.action == "formatting_dropped" for issue in issues)
    assert not any(issue.action == "retained_original" for issue in issues)


def test_complete_style_across_sentence_calls(odt_factory, tmp_path):
    calls = []

    class Sentences:
        def translate(self, text, **kwargs):
            calls.append(text)
            return {"Hello.": "Hallo.", "Bye.": "Tschüss."}[text]

    class Unresolved:
        def align(self, source, target):
            return AlignmentResult(source, target, unaligned=(TextRange(0, len(source)),))

    source = odt_factory(updates={"content.xml": document("<t:span>Hello. Bye.</t:span>")})
    output = tmp_path / "out.odt"
    translate_document(
        OdtReader(source),
        OdtWriter(source),
        Sentences(),
        output,
        source_lang="en",
        target_lang="de",
        aligner=Unresolved(),
    )
    assert calls == ["Hello.", "Bye."]
    with ZipFile(output) as archive:
        assert archive.read("content.xml") == document("<t:span>Hallo. Tschüss.</t:span>")


def test_marker_loss_retains_source_with_diagnostics(odt_factory, tmp_path):
    class MissingMarker:
        def translate(self, text, **kwargs):
            assert "<" not in text and "DLM" in text
            return "Hallo"

    class Unresolved:
        def align(self, source, target):
            return AlignmentResult(source, target, unaligned=(TextRange(0, len(source)),))

    xml = document("<t:span>Hello</t:span> <t:page-number>1</t:page-number>")
    source = odt_factory(updates={"content.xml": xml})
    output = tmp_path / "out.odt"
    issues = []
    translate_document(
        OdtReader(source),
        OdtWriter(source),
        MissingMarker(),
        output,
        source_lang="en",
        target_lang="de",
        aligner=Unresolved(),
        on_issue=issues.append,
    )
    with ZipFile(output) as archive:
        assert archive.read("content.xml") == xml
    assert any(issue.action == "retained_original" for issue in issues)


def test_writer_checks_rendered_evidence(odt_factory, tmp_path):
    source = odt_factory(updates={"content.xml": document("<t:span>Hello</t:span>")})
    segment = inline("<t:span>Hello</t:span>")
    restored = RestoredFormatting("Hallo", FormattingProjection((), ()))
    output = tmp_path / "out.odt"
    with pytest.raises(OdtPackageError, match="mismatch"):
        OdtWriter(source).write(
            output,
            [
                AlignedOdtSegment(
                    segment.id, "<t:span>injected</t:span>", segment.type, restored=restored
                )
            ],
        )
    assert not output.exists()


@pytest.mark.parametrize("attribute", ['xmlns:q="urn:local"', 'xml:id="unique"'])
def test_identity_or_namespace_scopes_use_protected_path(attribute):
    assert not supports_projection(inline(f"<t:span {attribute}>Hello</t:span>"))


def test_renderer_rejects_cutting_opaque_content():
    source = inline("<t:span>Hello <t:page-number>1</t:page-number></t:span>")
    scope = odt_scopes(source)[0]
    text = "Hallo <t:page-number>1</t:page-number>"
    restored = RestoredFormatting(
        text, FormattingProjection((ProjectedFormatting(scope, (TextRange(0, 10),)),), ())
    )
    with pytest.raises(OdtPackageError, match="splits protected"):
        render_aligned(source, restored)
    with pytest.raises(OdtPackageError, match="protection changed"):
        render_aligned(source, replace(restored, text="Hallo"))


def test_crossing_styles_are_dropped():
    source = inline("<t:span>one</t:span> <t:span>two</t:span>")
    scopes = odt_scopes(source)
    restored = RestoredFormatting(
        "eins zwei drei",
        FormattingProjection(
            (
                ProjectedFormatting(scopes[0], (TextRange(0, 9),)),
                ProjectedFormatting(scopes[1], (TextRange(5, 14),)),
            ),
            (),
        ),
    )
    text, issues = render_aligned(source, restored)
    assert text == "eins zwei drei"
    assert len(issues) == 2
    assert all(issue.action == "dropped" for issue in issues)


def test_protected_field_survives_aligned_translation(odt_factory, tmp_path):
    class Backend:
        def translate(self, text, **kwargs):
            assert "<" not in text and "DLM" in text
            return text.replace("Page", "Seite")

    class Aligner:
        def align(self, source, target):
            return AlignmentResult(source, target, unaligned=(TextRange(0, len(source)),))

    xml = document("<t:span>Page <t:page-number>1</t:page-number></t:span>")
    source = odt_factory(updates={"content.xml": xml})
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
        assert archive.read("content.xml") == xml.replace(b"Page", b"Seite")


def test_namespace_fallback_does_not_call_aligner(odt_factory, tmp_path):
    class Backend:
        def translate(self, text, **kwargs):
            assert text == "Hello"
            return "Hallo"

    class UnexpectedAligner:
        def align(self, source, target):
            pytest.fail("Namespace-owned wrapper must stay on protected path")

    xml = document('<t:span xmlns:q="urn:local">Hello</t:span>')
    source = odt_factory(updates={"content.xml": xml})
    output = tmp_path / "out.odt"
    translate_document(
        OdtReader(source),
        OdtWriter(source),
        Backend(),
        output,
        source_lang="en",
        target_lang="de",
        aligner=UnexpectedAligner(),
    )
    with ZipFile(output) as archive:
        assert archive.read("content.xml") == xml.replace(b"Hello", b"Hallo")
