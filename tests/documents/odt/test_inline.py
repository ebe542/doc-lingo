"""Inline preservation through the model-free translation service."""

from zipfile import ZipFile

import pytest

from doc_lingo import translate_document
from doc_lingo.documents.models import TextSegment
from doc_lingo.documents.odt import OdtPackageError, OdtReader, OdtWriter
from doc_lingo.documents.odt.blocks import text_blocks
from doc_lingo.documents.odt.inline import OdtInlineSegment


def document(body):
    return f"""<o:document-content
 xmlns:o="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:t="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
 xmlns:d="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
 xmlns:x="http://www.w3.org/1999/xlink">
 <o:body><o:text>{body}</o:text></o:body></o:document-content>""".encode()


def test_nested_styles_links_and_opaque_content(odt_factory, tmp_path):
    body = """<t:p>Hello <t:span t:style-name="Bold">dear
<t:a x:href="https://example.org/?a=1&amp;b=2"><t:span>reader</t:span></t:a></t:span>!
<t:s t:c="2"/><t:tab/><t:line-break/><t:bookmark t:name="anchor"/>
<t:page-number>1</t:page-number><t:sequence t:name="Figure">2</t:sequence>
<d:frame><!-- keep --><d:text-box><t:p>Hidden</t:p></d:text-box></d:frame></t:p>"""
    xml = document(body)
    source = odt_factory(updates={"content.xml": xml})
    calls = []

    class Backend:
        def translate(self, text, **kwargs):
            calls.append(text)
            return (
                text.replace("Hello", "Hallo").replace("dear", "lieber").replace("reader", "Leser")
            )

    output = tmp_path / "out.odt"
    translate_document(
        OdtReader(source), OdtWriter(source), Backend(), output, source_lang="en", target_lang="de"
    )
    assert len(calls) == 1
    assert all(word in calls[0] for word in ("Hello", "dear", "reader"))
    assert all(word not in calls[0] for word in ("<", "Bold", "https://", "Hidden", "Figure"))
    with ZipFile(source) as original, ZipFile(output) as translated:
        assert translated.read("content.xml") == xml.replace(b"Hello", b"Hallo").replace(
            b"dear", b"lieber"
        ).replace(b"reader", b"Leser")
        for name in original.namelist():
            if name != "content.xml":
                assert translated.read(name) == original.read(name)


def test_marker_loss_retains_paragraph_and_continues(odt_factory, tmp_path):
    xml = document("<t:p>Hello <t:span>reader</t:span>!</t:p><t:p>Next</t:p>")
    source = odt_factory(updates={"content.xml": xml})
    issues = []

    class Backend:
        def translate(self, text, **kwargs):
            return "Weiter" if text == "Next" else "Hallo Leser!"

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
    assert any(issue.action == "retained_original" for issue in issues)
    with ZipFile(output) as archive:
        assert archive.read("content.xml") == xml.replace(b">Next<", b">Weiter<")


@pytest.mark.parametrize("mode", ["missing", "duplicate", "order", "empty", "invalid"])
def test_writer_rejects_damaged_inline_without_publication(odt_factory, tmp_path, mode):
    source = odt_factory(
        updates={"content.xml": document("<t:p>Hello <t:span>reader</t:span>!</t:p>")}
    )
    with OdtReader(source).iter_segments() as values:
        segment = next(values)
    text = {
        "missing": "Hallo Leser!",
        "duplicate": "Hallo <t:span>Leser</t:span><t:span>!",
        "order": "Hallo </t:span>Leser<t:span>!",
        "empty": "<t:span></t:span>",
        "invalid": "Hallo <t:span>Leser</t:span>\x00",
    }[mode]
    assert not segment.accepts_translation(text)
    output = tmp_path / "out.odt"
    # Service results carry translated text, not source-local protected ranges.
    translated = TextSegment(segment.id, text, segment.type)
    with pytest.raises(OdtPackageError):
        OdtWriter(source).write(output, [translated])
    assert not output.exists()


def test_entities_aliases_and_empty_inline_elements():
    xml = document(
        '<t:p>caf&#233; <t:span t:style-name="a&gt;b">&amp; tea</t:span>'
        "<t:span/><t:tab></t:tab></t:p>"
    )
    block = text_blocks(xml)[0]
    assert block.reason is None
    assert isinstance(block.segment, OdtInlineSegment)
    assert block.segment.text.startswith('café <t:span t:style-name="a&gt;b">& tea')
    rendered = block.segment.render(block.segment.text.replace("tea", "<Tee>"))
    assert b"&amp; &lt;Tee&gt;" in rendered
    assert rendered.endswith(b"<t:span/><t:tab></t:tab>")


@pytest.mark.parametrize(
    "body,reason",
    [
        ("<t:p>Hello <t:unknown>world</t:unknown></t:p>", "inline_content"),
        ("<t:p><t:page-number>1</t:page-number></t:p>", "protected_only"),
        ("<t:p>Hello<!-- comment --><t:span>world</t:span></t:p>", "inline_content"),
    ],
)
def test_unsupported_or_fully_protected_blocks_remain_skipped(body, reason):
    assert text_blocks(document(body))[0].reason == reason
