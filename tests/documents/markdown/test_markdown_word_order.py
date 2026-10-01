"""Allow translated word movement while retaining actual Markdown structure."""

import re

import pytest

from doc_lingo import (
    MarkdownReader,
    MarkdownWriter,
    SegmentMismatchError,
    TextSegment,
    translate_document,
)


def test_code_can_move_to_sentence_start_without_source_fallback(tmp_path):
    source = tmp_path / "source.md"
    source.write_bytes(b"Keep `model.predict(data)` unchanged and review the result.")
    destination = tmp_path / "translated.md"
    calls = []

    class Backend:
        def translate(self, text, **kwargs):
            calls.append(text)
            marker = re.search(r"DLM[0-9A-F]+X0Z", text)
            assert marker is not None
            return marker.group() + " unverändert aufbewahren und das Ergebnis überprüfen."

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
    assert destination.read_text(encoding="utf-8") == (
        "`model.predict(data)` unverändert aufbewahren und das Ergebnis überprüfen."
    )
    assert len(calls) == 1
    assert not issues


@pytest.mark.parametrize(
    "original,translated",
    [
        ("Read [the guide](/guide).", "[Die Anleitung](/guide) lesen."),
        ("Use **this model**.", "**Dieses Modell** verwenden."),
        ("Use *this model*.", "*Dieses Modell* verwenden."),
        ("Read [the `guide` now](/guide).", "[Jetzt das `guide`](/guide) lesen."),
        ("`code` first", "Zuerst `code`"),
    ],
)
def test_writer_accepts_plain_text_reordering(tmp_path, original, translated):
    source = tmp_path / "source.md"
    source.write_text(original, encoding="utf-8")
    destination = tmp_path / "output.md"
    MarkdownWriter(source).write(destination, [TextSegment("1", translated)])
    assert destination.read_text(encoding="utf-8") == translated


@pytest.mark.parametrize(
    "original,translated",
    [
        ("Keep `code` unchanged.", "`changed` unverändert lassen."),
        ("Read [the guide](/guide).", "[Anleitung](/different) lesen."),
        ("Read [the guide](/guide).", "Anleitung lesen. [ ](/guide)"),
        ("Use **this model**.", "Dieses Modell verwenden. ** **"),
        ("Read [**the guide**](/guide).", "**[Anleitung](/guide)** lesen."),
        ("Hello", "# Hallo"),
        ("Hello  \nworld", "Hallo\nWelt"),
    ],
)
def test_writer_still_rejects_structural_changes(tmp_path, original, translated):
    source = tmp_path / "source.md"
    source.write_bytes(original.encode())
    with pytest.raises(SegmentMismatchError):
        MarkdownWriter(source).write(tmp_path / "output.md", [TextSegment("1", translated)])
    assert list(tmp_path.iterdir()) == [source]
