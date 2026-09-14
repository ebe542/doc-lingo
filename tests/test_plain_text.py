"""Verify paragraph extraction and reading-session resource ownership."""

from pathlib import Path

import pytest

from doc_lingo import PlainTextReader, TextSegment


@pytest.mark.parametrize(
    ("content", "paragraphs"),
    [
        ("", []),
        ("\n \t\n", []),
        ("First paragraph.\n\nSecond paragraph.", ["First paragraph.\n", "Second paragraph."]),
        ("\n\nFirst\n \t\n\nSecond\n\n", ["First\n", "Second\n"]),
        ("One\ncontinued\n", ["One\ncontinued\n"]),
        ("Grüße\r\n\r\nWelt\r", ["Grüße\r\n", "Welt\r"]),
        ("\ufeffHello", ["Hello"]),
        ("\ufeff", []),
    ],
)
def test_paragraphs_preserve_text_and_have_repeatable_ids(tmp_path, content, paragraphs):
    path = tmp_path / "source.txt"
    original = content.encode("utf-8")
    path.write_bytes(original)
    reader = PlainTextReader(path)
    expected = [TextSegment(str(index), text) for index, text in enumerate(paragraphs, 1)]

    for _ in range(2):
        with reader.iter_segments() as segments:
            assert list(segments) == expected
    assert path.read_bytes() == original


def test_missing_file_fails_on_context_entry(tmp_path):
    reader = PlainTextReader(str(tmp_path / "missing.txt"))
    with pytest.raises(FileNotFoundError), reader.iter_segments():
        pytest.fail("A missing source must not open a reading session")


@pytest.mark.parametrize("mode", ["complete", "early", "unused", "consumer_error", "invalid_utf8"])
def test_session_closes_file_and_iterator(tmp_path, monkeypatch, mode):
    path = tmp_path / "source.txt"
    path.write_bytes(b"\xff" if mode == "invalid_utf8" else b"First\n\nSecond")
    opened = []
    original_open = Path.open

    def track_open(self, *args, **kwargs):
        stream = original_open(self, *args, **kwargs)
        opened.append(stream)
        return stream

    monkeypatch.setattr(Path, "open", track_open)
    reader = PlainTextReader(path)
    assert not opened

    class ConsumerError(Exception):
        pass

    def consume():
        if mode == "complete":
            assert len(list(segments)) == 2
        elif mode == "invalid_utf8":
            list(segments)
        elif mode != "unused":
            assert next(segments).text == "First\n"
            if mode == "consumer_error":
                raise ConsumerError

    if mode in {"consumer_error", "invalid_utf8"}:
        error = ConsumerError if mode == "consumer_error" else UnicodeDecodeError
        with pytest.raises(error), reader.iter_segments() as segments:
            consume()
    else:
        with reader.iter_segments() as segments:
            consume()

    assert len(opened) == 1
    assert opened[0].closed
    assert list(segments) == []
