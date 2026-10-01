"""Keep wrapped list items together for translation and reconstruction."""

import pytest

from doc_lingo import PlainTextReader, PlainTextWriter, TextSegment, translate_document


@pytest.mark.parametrize(
    ("marker", "kind"),
    [
        ("-", "bullet_item"),
        ("*", "bullet_item"),
        ("•", "bullet_item"),
        ("3.", "numbered_item"),
        ("3)", "numbered_item"),
    ],
)
@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("indent", ["", "  ", "\t"])
def test_complete_item_reaches_backend_once(tmp_path, marker, kind, newline, indent):
    source = tmp_path / "source.txt"
    output = tmp_path / "output.txt"
    body = f"Regression or{newline}{indent}classification.{newline}One more line.{newline}"
    original = f"\ufeffIntro{newline}{marker} {body}- Next{newline}{newline}Prose"
    source.write_bytes(original.encode())
    calls = []
    progress = []

    class Backend:
        def translate(self, text, *, source_lang, target_lang):
            calls.append(text)
            return text.replace("classification", "Klassifikation")

    with PlainTextReader(source).iter_segments() as segments:
        assert list(segments) == [
            TextSegment("1", f"Intro{newline}"),
            TextSegment("2", body, kind),
            TextSegment("3", f"Next{newline}", "bullet_item"),
            TextSegment("4", "Prose"),
        ]
    translate_document(
        PlainTextReader(source),
        PlainTextWriter(source),
        Backend(),
        output,
        source_lang="en",
        target_lang="de",
        on_progress=lambda count, segment_type: progress.append((count, segment_type)),
    )
    assert calls == [f"Intro{newline}", body, f"Next{newline}", "Prose"]
    assert progress == [(1, "paragraph"), (2, kind), (3, "bullet_item"), (4, "paragraph")]
    assert output.read_bytes() == original.replace("classification", "Klassifikation").encode()
    assert source.read_bytes() == original.encode()


def test_wrapped_last_item_at_eof_and_blank_line_reset(tmp_path):
    source = tmp_path / "source.txt"
    output = tmp_path / "output.txt"
    original = "- First\ncontinued\n \t\nProse\ncontinued prose\n1) Last\n  final line"
    source.write_bytes(original.encode())
    with PlainTextReader(source).iter_segments() as segments:
        extracted = list(segments)
    assert extracted == [
        TextSegment("1", "First\ncontinued\n", "bullet_item"),
        TextSegment("2", "Prose\ncontinued prose\n"),
        TextSegment("3", "Last\n  final line", "numbered_item"),
    ]
    PlainTextWriter(source).write(output, extracted)
    assert output.read_bytes() == original.encode()
