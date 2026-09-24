"""Markdown integration without model loading or inference."""

import re

import pytest

from doc_lingo import (
    Glossary,
    GlossaryBackend,
    GlossaryEntry,
    MarkdownReader,
    MarkdownWriter,
    RecoverableTranslationError,
    SegmentMismatchError,
    TextSegment,
    translate_document,
)
from doc_lingo.interfaces import cli
from doc_lingo.translation.issues import retain_original


class Backend:
    def __init__(self):
        self.calls = []

    def translate(self, text, *, source_lang, target_lang):
        self.calls.append(text)
        return text.replace("Hello", "Hallo").replace("world", "Welt")


def run_translation(tmp_path, content, backend=None, **kwargs):
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
    return source, destination, backend


@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("bom", ["", "\ufeff"])
def test_markup_and_continuation_context(tmp_path, ending, bom):
    content = bom + ending.join(
        [
            "# Hello #",
            "",
            'Hello **world** and [Hello](https://example.org/a_(b) "Title").',
            "",
            "- Hello",
            "  world",
            "",
            "1. Hello",
            "",
            "> Hello",
            "",
            "Hello",
            "=====",
            "",
        ]
    )
    source, destination, backend = run_translation(tmp_path, content)
    assert (
        destination.read_bytes()
        == content.replace("Hello", "Hallo").replace("world", "Welt").encode()
    )
    assert source.read_bytes() == content.encode()
    assert len(backend.calls) == 6
    assert any("Hello" in call and "world" in call for call in backend.calls)
    assert all("https://" not in call for call in backend.calls)
    with MarkdownReader(source).iter_segments() as segments:
        assert [s.type for s in segments] == [
            "heading",
            "paragraph",
            "bullet_item",
            "numbered_item",
            "blockquote",
            "heading",
        ]


@pytest.mark.parametrize(
    "content",
    [
        "",
        "\ufeff",
        "\n \t\n",
        "Hello",
        "Hello\ncontinued\n\nworld\n",
        "# Hello\n\n- Hello\n  world\n",
        "Hello  \nworld\n",
        "Hello\\\nworld\n",
        "Hello *world* and ~~Hello~~.\n",
        "Hello `code` and ``a ` b``.\n",
        "Hello &amp; world and \\*literal\\*.\n",
        "[Hello](<https://example.org> 'Title')\n",
        "1. 1\n\n# # #\n",
        "---\ntitle: Hello\n---\n\nHello\n",
    ],
)
def test_identity_roundtrip(tmp_path, content):
    class Identity:
        def translate(self, text, **kwargs):
            return text

    source, destination, _ = run_translation(tmp_path, content, Identity())
    assert destination.read_bytes() == source.read_bytes()
    assert set(tmp_path.iterdir()) == {source, destination}


@pytest.mark.parametrize(
    "protected",
    [
        "```python\nHello = 1\n```\n",
        "~~~\nHello\n~~~\n",
        "    Hello\n",
        "<div>\nHello\n</div>\n",
        "Hello <span>world</span>.\n",
        '![Hello](image.png "Hello")\n',
        "[Hello]\n\n[Hello]: https://example.org\n",
        "[Hello][]\n\n[Hello]: https://example.org\n",
        "<https://example.org/Hello>\n",
        "---\ntitle: Hello\n---\n",
        "---\ntitle: Hello\n",
    ],
)
def test_unsupported_or_nonprose_is_unchanged(tmp_path, protected):
    _, destination, backend = run_translation(tmp_path, protected)
    assert destination.read_bytes() == protected.encode()
    assert not backend.calls


def test_code_and_reference_destination_are_not_sent_to_backend(tmp_path):
    content = 'Hello `world` and [world][manual].\n\n[manual]: /world "Hello"\n'
    _, destination, backend = run_translation(tmp_path, content)
    assert destination.read_bytes() == (
        b'Hallo `world` and [Welt][manual].\n\n[manual]: /world "Hello"\n'
    )
    assert len(backend.calls) == 1
    assert "manual" not in backend.calls[0]


def test_glossary_composes_with_markdown_protection(tmp_path):
    backend = GlossaryBackend(Backend(), Glossary("en", "de", (GlossaryEntry("world", "keep"),)))
    _, destination, _ = run_translation(tmp_path, "Hello **world** again.\n", backend)
    assert destination.read_bytes() == b"Hallo **world** again.\n"


def test_nested_lists_keep_the_innermost_type(tmp_path):
    source = tmp_path / "source.md"
    source.write_bytes(b"1. Hello\n   - world\n")
    with MarkdownReader(source).iter_segments() as segments:
        assert [segment.type for segment in segments] == ["numbered_item", "bullet_item"]


@pytest.mark.parametrize("failure", ["missing", "duplicate", "reordered", "recovery", "markup"])
def test_unsafe_translation_retains_whole_segment_and_continues(tmp_path, failure):
    class Broken(Backend):
        def translate(self, text, **kwargs):
            if "DLM" not in text:
                return super().translate(text, **kwargs)
            markers = re.findall(r"DLM[0-9A-F]+X[0-9]+Z", text)
            if failure == "missing":
                return text.replace(markers[0], "")
            if failure == "duplicate":
                return text + markers[0]
            if failure == "reordered":
                return (
                    text.replace(markers[0], "TEMP")
                    .replace(markers[1], markers[0])
                    .replace("TEMP", markers[1])
                )
            if failure == "recovery":
                return retain_original(text, "Model failed")
            return "# " + text

    issues = []
    content = "Hello **world** again.\n\nHello\n"
    _, destination, _ = run_translation(tmp_path, content, Broken(), on_issue=issues.append)
    assert destination.read_bytes() == b"Hello **world** again.\n\nHallo\n"
    assert len(issues) == 1
    assert issues[0].segment_id == "1"
    assert issues[0].original == "Hello **world** again.\n"
    assert "DLM" not in str(issues)


def test_strict_library_rejects_changed_structure(tmp_path):
    class Broken:
        def translate(self, text, **kwargs):
            return "# " + text

    with pytest.raises(RecoverableTranslationError):
        run_translation(tmp_path, "Hello\n", Broken())
    assert {p.name for p in tmp_path.iterdir()} == {"source.md"}


@pytest.mark.parametrize("ids", [[], ["1"], ["2", "1"], ["1", "2", "3"]])
def test_invalid_segment_sequence_cleans_up(tmp_path, ids):
    source = tmp_path / "source.md"
    source.write_bytes(b"Hello\n\nworld\n")
    with pytest.raises(SegmentMismatchError):
        MarkdownWriter(source).write(
            tmp_path / "output.md", (TextSegment(id_, "Text\n") for id_ in ids)
        )
    assert list(tmp_path.iterdir()) == [source]


def test_writer_rejects_direct_structure_change(tmp_path):
    source = tmp_path / "source.md"
    source.write_bytes(b"# Hello\n")
    with pytest.raises(SegmentMismatchError):
        MarkdownWriter(source).write(tmp_path / "output.md", [TextSegment("1", "Hello\n")])
    assert list(tmp_path.iterdir()) == [source]


def test_writer_never_overwrites_source(tmp_path):
    source = tmp_path / "source.md"
    source.write_bytes(b"Hello")
    with pytest.raises(FileExistsError):
        MarkdownWriter(source).write(source, [])
    assert source.read_bytes() == b"Hello"


@pytest.mark.parametrize("extension", [".md", ".MD"])
def test_cli_selects_markdown(tmp_path, monkeypatch, capsys, extension):
    source = tmp_path / ("book" + extension)
    source.write_bytes(b"# Hello\n\nHello **world** again.\n")
    monkeypatch.setattr(cli, "MarianBackend", Backend)
    monkeypatch.setattr(cli, "load_dotenv", lambda **kwargs: None)
    cli.main([str(source), "--target-lang", "de"])
    assert (tmp_path / "book.de.md").read_bytes() == b"# Hallo\n\nHallo **Welt** again.\n"
    assert "Type: heading" in capsys.readouterr().err
    assert not (tmp_path / "book.de.md.issues.jsonl").exists()


def test_cli_rejects_format_conversion(tmp_path):
    with pytest.raises(SystemExit) as error:
        cli.main(["book.md", "--target-lang", "de", "--output", str(tmp_path / "book.txt")])
    assert error.value.code == 2
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("ranges", [((1, 1),), ((0, 9),), ((1, 2), (0, 1))])
def test_invalid_protected_ranges_are_rejected(ranges):
    with pytest.raises(ValueError):
        TextSegment("1", "abc", protected_spans=ranges)
