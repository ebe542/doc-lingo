"""Table translation retains source cells, delimiters and alignment."""

import pytest

from doc_lingo import MarkdownReader, MarkdownWriter, translate_document


@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("border", [True, False])
def test_cells_translate_without_reformatting(tmp_path, ending, border):
    rows = [
        " Hello | world ",
        " :--- | ---: ",
        " **Hello** | [world](/path) ",
        r" Hello \| world | `code` ",
        "  | Hello ",
    ]
    content = "\ufeff" + ending.join(("|" + row + "|" if border else row) for row in rows)
    source = tmp_path / "source.md"
    source.write_bytes(content.encode())
    destination = tmp_path / "output.md"
    calls = []

    class Backend:
        def translate(self, text, **kwargs):
            calls.append(text)
            return text.replace("Hello", "Hallo").replace("world", "Welt")

    progress = []
    translate_document(
        MarkdownReader(source),
        MarkdownWriter(source),
        Backend(),
        destination,
        source_lang="en",
        target_lang="de",
        on_progress=lambda count, kind: progress.append(kind),
    )
    assert (
        destination.read_bytes()
        == content.replace("Hello", "Hallo").replace("world", "Welt").encode()
    )
    assert len(calls) == 6
    assert progress == ["table_cell"] * 6
    assert source.read_bytes() == content.encode()


@pytest.mark.parametrize("bad", ["new | column", "new\nrow", "new\rrow", "new\\"])
def test_invalid_cell_retained_and_following_cells_continue(tmp_path, bad):
    source = tmp_path / "source.md"
    source.write_bytes(b"| Hello | world |\n| --- | --- |\n| Hello | world |\n")
    destination = tmp_path / "output.md"

    class Backend:
        def translate(self, text, **kwargs):
            return bad if text == "Hello" else "Welt"

    issues = []
    translate_document(
        MarkdownReader(source),
        MarkdownWriter(source),
        Backend(),
        destination,
        source_lang="en",
        target_lang="de",
        on_issue=issues.append,
    )
    assert destination.read_bytes() == b"| Hello | Welt |\n| --- | --- |\n| Hello | Welt |\n"
    assert [issue.segment_type for issue in issues] == ["table_cell", "table_cell"]


def test_html_empty_missing_and_extra_cells_remain_unchanged(tmp_path):
    content = (
        "| Hello | world |\n| --- | --- |\n| <div>Hello</div> | |\n"
        "| Hello |\n| Hello | world | extra |\n"
    )
    source = tmp_path / "source.md"
    source.write_text(content, encoding="utf-8", newline="")
    with MarkdownReader(source).iter_segments() as segments:
        texts = [segment.text for segment in segments]
    assert texts == ["Hello", "world", "Hello", "Hello", "world"]

    class Identity:
        def translate(self, text, **kwargs):
            return text

    destination = tmp_path / "output.md"
    translate_document(
        MarkdownReader(source),
        MarkdownWriter(source),
        Identity(),
        destination,
        source_lang="en",
        target_lang="de",
    )
    assert destination.read_bytes() == source.read_bytes()
