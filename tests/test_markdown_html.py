"""Translate embedded HTML text while retaining exact source markup."""

import pytest

from doc_lingo import (
    MarkdownReader,
    MarkdownWriter,
    RecoverableTranslationError,
    SegmentMismatchError,
    TextSegment,
    translate_document,
)
from doc_lingo.documents.html.text import HtmlSegment


class Backend:
    def __init__(self):
        self.calls = []

    def translate(self, text, **kwargs):
        self.calls.append(text)
        return text.replace("Hello", "Hallo").replace("world", "Welt")


def translate(tmp_path, content, backend=None, **kwargs):
    source = tmp_path / "source.md"
    destination = tmp_path / "translated.md"
    source.write_bytes(content.encode())
    backend = backend or Backend()
    translate_document(
        MarkdownReader(source),
        MarkdownWriter(source),
        backend,
        destination,
        source_lang="en",
        target_lang="de",
        **kwargs,
    )
    return destination.read_bytes().decode(), backend


@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("bom", ["", "\ufeff"])
def test_block_translation_keeps_attributes_and_inline_context(tmp_path, ending, bom):
    content = bom + ending.join(
        [
            '<DIV class="Hello" title=world aria-label="Hello" data-note="a > b">',
            "  Hello <strong>world</strong>.",
            "</DIV>",
            "",
        ]
    )
    result, backend = translate(tmp_path, content)
    assert result == content.replace("  Hello <strong>world", "  Hallo <strong>Welt")
    assert len(backend.calls) == 1
    assert "Hello" in backend.calls[0] and "world" in backend.calls[0]
    assert "class" not in backend.calls[0]
    assert (tmp_path / "source.md").read_bytes() == content.encode()


def test_block_elements_define_independent_segments(tmp_path):
    content = (
        "<div><h2>Hello</h2><p>Hello <em>world</em>.</p>"
        "<ul><li>Hello</li><li>world</li></ul>"
        "<table><tr><th>Hello</th><td>world</td></tr></table></div>"
    )
    progress = []
    result, backend = translate(
        tmp_path, content, on_progress=lambda number, kind: progress.append(kind)
    )
    assert result == content.replace("Hello", "Hallo").replace("world", "Welt")
    assert len(backend.calls) == 6
    assert progress == ["html_text"] * 6


@pytest.mark.parametrize("wrapper", ["{}", "| {} |\n| --- |\n", "- {}\n", "> {}\n"])
def test_inline_html_in_markdown_and_table_cells(tmp_path, wrapper):
    content = wrapper.format('Hello <span title="Hello">world</span> and **Hello**.')
    result, backend = translate(tmp_path, content)
    assert result == wrapper.format('Hallo <span title="Hello">Welt</span> and **Hallo**.')
    assert len(backend.calls) == 1


@pytest.mark.parametrize("tag", ["script", "style", "pre", "code", "head", "template"])
def test_excluded_element_contents_never_reach_model(tmp_path, tag):
    content = f"<div>Hello <{tag}>world</{tag}> Hello</div>\n"
    result, backend = translate(tmp_path, content)
    assert result == content.replace("Hello", "Hallo")
    assert all("world" not in call for call in backend.calls)


@pytest.mark.parametrize("attribute", ['translate="no"', "TRANSLATE='NO'", "hidden"])
def test_exclusion_is_inherited_across_markdown_blocks(tmp_path, attribute):
    content = (
        f"<div {attribute}>\n\nHello <span translate='yes'>world</span>.\n\n"
        "- Hello\n\n</div>\n\nHello\n"
    )
    result, backend = translate(tmp_path, content)
    assert result == content[:-6] + "Hallo\n"
    assert backend.calls == ["Hello"] or backend.calls == ["Hello\n"]


def test_open_html_context_across_blank_lines(tmp_path):
    content = "<div>\n\nHello <strong>world</strong>.\n\n</div>\n"
    result, backend = translate(tmp_path, content)
    assert result == content.replace("Hello", "Hallo").replace("world", "Welt")
    assert len(backend.calls) == 1


def test_comments_entities_void_tags_and_code_spelling_are_retained(tmp_path):
    content = (
        "<div>Hello &amp; world &#160; &#xA0; <!-- Hello -->"
        '<br><img alt="Hello" src="world.png" />'
        "<code>Hello &lt;world&gt;</code> Hello</div>\n"
    )
    result, _ = translate(tmp_path, content)
    assert result == content.replace("<div>Hello &amp; world", "<div>Hallo &amp; Welt").replace(
        "</code> Hello", "</code> Hallo"
    )


def test_markdown_code_containing_html_does_not_change_exclusion_context(tmp_path):
    content = "Use `<span translate='no'>` with Hello <em>world</em>.\n\nHello\n"
    result, backend = translate(tmp_path, content)
    assert result == content.replace("Hello", "Hallo").replace("world", "Welt")
    assert len(backend.calls) == 2


def test_leading_autolink_is_not_mistaken_for_an_unfinished_html_tag(tmp_path):
    content = "<https://example.org/Hello> Hello <em>world</em>.\n"
    result, backend = translate(tmp_path, content)
    assert result == "<https://example.org/Hello> Hallo <em>Welt</em>.\n"
    assert len(backend.calls) == 1


@pytest.mark.parametrize("declaration", ["<![unsupported[Hello]]>", "<!unsupported Hello>"])
def test_unsupported_html_parser_declaration_is_retained(declaration):
    from doc_lingo.documents.html.text import HtmlText

    assert not HtmlText(declaration).safe


def test_unsupported_declaration_retains_containing_fragment(tmp_path):
    content = "<div>Hello <![unsupported[world]]></div>\n\nHello\n"
    result, backend = translate(tmp_path, content)
    assert result == "<div>Hello <![unsupported[world]]></div>\n\nHallo\n"
    assert len(backend.calls) == 1


@pytest.mark.parametrize(
    "content",
    [
        "<div>Hello</span></div>\n",
        "<!-- Hello -->\n",
        "<!DOCTYPE html>\n",
        "<?instruction Hello?>\n",
        "<![CDATA[Hello]]>\n",
        "<!-- Hello\n",
        "<script>const text = '<div>Hello</div>';</script>\n",
    ],
)
def test_nonprose_and_mismatched_source_are_preserved(tmp_path, content):
    result, backend = translate(tmp_path, content)
    assert result == content
    assert not backend.calls


@pytest.mark.parametrize("source", ["<div>Hello</div>\n", "Hello <span>world</span>.\n"])
def test_generated_markup_retains_source_and_reports_issue(tmp_path, source):
    class Broken(Backend):
        def translate(self, text, **kwargs):
            return '<img src="unexpected.png">' + text

    issues = []
    result, _ = translate(tmp_path, source, Broken(), on_issue=issues.append)
    assert result == source
    assert len(issues) == 1
    assert "DLM" not in issues[0].original


def test_strict_library_rejects_generated_html(tmp_path):
    class Broken:
        def translate(self, text, **kwargs):
            return "<b>Hallo</b>"

    with pytest.raises(RecoverableTranslationError):
        translate(tmp_path, "<div>Hello</div>\n", Broken())
    assert {p.name for p in tmp_path.iterdir()} == {"source.md"}


def test_quoted_html_block_is_retained_when_source_mapping_differs(tmp_path):
    content = "> <div>Hello</div>\n"
    result, backend = translate(tmp_path, content)
    assert result == content
    assert not backend.calls


def test_direct_writer_rejects_attribute_changes(tmp_path):
    source = tmp_path / "source.md"
    source.write_bytes(b'Hello <span title="original">world</span>.')
    with pytest.raises(SegmentMismatchError):
        MarkdownWriter(source).write(
            tmp_path / "output.md", [TextSegment("1", 'Hallo <span title="changed">Welt</span>.')]
        )
    assert {p.name for p in tmp_path.iterdir()} == {"source.md"}


@pytest.mark.parametrize("wrapper", ["<div>{}</div>\n", "{}\n", "| {} |\n| --- |\n"])
@pytest.mark.parametrize("tag", ["strong class='important'", "span", "a href='/guide'"])
def test_emptied_inline_element_retains_original_and_continues(tmp_path, wrapper, tag):
    closing = tag.split()[0]
    original = wrapper.format(f"Hello <{tag}>world</{closing}>.")

    class MovedText(Backend):
        def translate(self, text, **kwargs):
            if "world" in text:
                return "Welt " + text.replace("world", "").replace("Hello", "Hallo")
            return super().translate(text, **kwargs)

    issues = []
    result, _ = translate(tmp_path, original + "\nHello\n", MovedText(), on_issue=issues.append)
    assert result == original + "\nHallo\n"
    assert len(issues) == 1
    assert "DLM" not in issues[0].original


@pytest.mark.parametrize("empty", ["", " ", "\n", "&nbsp;", "<!-- empty -->"])
def test_nested_emphasis_cannot_be_emptied(empty):
    segment = HtmlSegment("1", "Hello <strong><em>world</em></strong>.")
    assert not segment.accepts_translation(f"Hallo Welt <strong><em>{empty}</em></strong>.")
    assert segment.accepts_translation("Hallo <strong><em>Welt</em></strong>.")


def test_existing_empty_and_entity_only_elements_are_handled():
    assert HtmlSegment("1", "Hello <span></span>.").accepts_translation("Hallo <span></span>.")
    assert HtmlSegment("1", "Hello <strong>&amp;</strong>.").accepts_translation(
        "Hallo <strong>&amp;</strong>."
    )
    assert not HtmlSegment("1", "<span>Hello</span><span>world</span>").accepts_translation(
        "<span>Hallo Welt</span><span></span>"
    )


@pytest.mark.parametrize("wrapper", ["<div>{}</div>\n", "{}\n", "| {} |\n| --- |\n"])
@pytest.mark.parametrize("tag", ["strong", "em", "b", "i"])
def test_empty_emphasis_is_removed_and_translation_kept(tmp_path, wrapper, tag):
    original = wrapper.format(f"Hello <{tag}>world</{tag}>.")

    class MovedText(Backend):
        def translate(self, text, **kwargs):
            return "Welt " + text.replace("world", "").replace("Hello", "Hallo")

    issues = []
    result, _ = translate(tmp_path, original, MovedText(), on_issue=issues.append)
    assert result == wrapper.format("Welt Hallo .")
    assert len(issues) == 1
    assert issues[0].action == "formatting_repaired"
    assert "Translation retained" in issues[0].reason


def test_nested_empty_emphasis_repair_is_validated():
    segment = HtmlSegment("1", "Hello <strong><em>world</em></strong>.")
    assert segment.repair_translation("Hallo Welt <strong><em></em></strong>.") == "Hallo Welt ."
    assert segment.repair_translation("Hallo Welt <strong><em></em></strong><img src='x'>.") is None
    assert segment.repair_translation("Hallo <strong><em>Welt</em></strong>.") is None
    assert segment.repair_translation("Hallo Welt <strong><em><!-- note --></em></strong>.") is None


def test_empty_emphasis_repair_requires_issue_callback(tmp_path):
    class MovedText(Backend):
        def translate(self, text, **kwargs):
            return "Welt " + text.replace("world", "")

    with pytest.raises(RecoverableTranslationError):
        translate(tmp_path, "<div>Hello <strong>world</strong>.</div>", MovedText())
    assert {p.name for p in tmp_path.iterdir()} == {"source.md"}


def test_cli_distinguishes_formatting_repairs(tmp_path, monkeypatch, capsys):
    import json

    from doc_lingo.interfaces import cli

    source = tmp_path / "example.md"
    source.write_bytes(b"<div>Hello <strong>world</strong>.</div>")

    class MovedText(Backend):
        def translate(self, text, **kwargs):
            return "Welt " + text.replace("world", "").replace("Hello", "Hallo")

    monkeypatch.setattr(cli, "MarianBackend", MovedText)
    monkeypatch.setattr(cli, "load_dotenv", lambda **kwargs: None)
    with pytest.raises(SystemExit) as error:
        cli.main([str(source), "--target-lang", "de"])
    assert error.value.code == 3
    assert (tmp_path / "example.de.md").read_bytes() == b"<div>Welt Hallo .</div>"
    issue = json.loads((tmp_path / "example.de.md.issues.jsonl").read_text(encoding="utf-8"))
    assert issue["action"] == "formatting_repaired"
    assert issue["diagnostics"]["stage"] == "restored"
    assert "<strong></strong>" in issue["diagnostics"]["attempted_translation"]
    assert "html_text_emptied: strong[0]" in issue["diagnostics"]["validation_errors"]
    output = capsys.readouterr()
    assert "formatting warnings" in output.out
    assert "0 original text units retained" in output.err
    assert "1 segments with formatting repaired" in output.err


def test_writer_rechecks_repair_instead_of_trusting_metadata(tmp_path):
    source = tmp_path / "source.md"
    source.write_bytes(b"Hello <strong>world</strong>.")
    with pytest.raises(SegmentMismatchError):
        MarkdownWriter(source).write(
            tmp_path / "output.md",
            [
                TextSegment(
                    "1",
                    "<img src='unexpected'>Welt Hallo .",
                    unrepaired_text="Welt Hallo <strong></strong>.",
                )
            ],
        )
    assert {p.name for p in tmp_path.iterdir()} == {"source.md"}
