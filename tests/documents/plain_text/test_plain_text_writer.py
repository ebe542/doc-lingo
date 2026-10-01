"""Check TXT reconstruction, validation, and safe output publication."""

import os

import pytest

from doc_lingo import PlainTextReader, PlainTextWriter, SegmentMismatchError, TextSegment


@pytest.mark.parametrize(
    "content",
    [
        "",
        "\ufeff",
        "\n \t\r\n",
        "One",
        "One\ncontinued\n\nTwo\n\n",
        "\ufeffGrüße\r\n\r\nWelt\r",
        "\nFirst\r\n \t\r\n\nSecond",
    ],
)
def test_identity_translation_preserves_original_bytes(tmp_path, content):
    source = tmp_path / "source.txt"
    destination = tmp_path / "translated.txt"
    original = content.encode("utf-8")
    source.write_bytes(original)

    with PlainTextReader(source).iter_segments() as segments:
        PlainTextWriter(str(source)).write(destination, segments)

    assert destination.read_bytes() == original
    assert source.read_bytes() == original
    assert set(tmp_path.iterdir()) == {source, destination}


def test_translation_preserves_separators_and_original_endings(tmp_path):
    source = tmp_path / "source.txt"
    destination = tmp_path / "translated.txt"
    original = "\ufeff\nFirst\r\ncontinued\r\n \t\r\nSecond"
    source.write_bytes(original.encode("utf-8"))
    translations = iter([TextSegment("1", "Erste\nFortsetzung\n"), TextSegment("2", "Zweite\n")])

    PlainTextWriter(source).write(destination, translations)

    assert destination.read_bytes() == "\ufeff\nErste\nFortsetzung\r\n \t\r\nZweite".encode()
    assert source.read_bytes() == original.encode()


@pytest.mark.parametrize("ids", [[], ["1"], ["2", "1"], ["1", "1"], ["1", "2", "3"]])
def test_mismatched_ids_leave_no_output_or_temporary_files(tmp_path, ids):
    source = tmp_path / "source.txt"
    source.write_bytes(b"First\n\nSecond")
    destination = tmp_path / "translated.txt"

    with pytest.raises(SegmentMismatchError):
        PlainTextWriter(source).write(destination, (TextSegment(id_, "Text") for id_ in ids))

    assert list(tmp_path.iterdir()) == [source]
    assert source.read_bytes() == b"First\n\nSecond"


@pytest.mark.parametrize("use_source", [False, True])
def test_existing_destination_is_never_overwritten(tmp_path, use_source):
    source = tmp_path / "source.txt"
    source.write_bytes(b"Original")
    destination = source if use_source else tmp_path / "translated.txt"
    if not use_source:
        destination.write_bytes(b"Existing output")
    before = {path: path.read_bytes() for path in tmp_path.iterdir()}

    with pytest.raises(FileExistsError):
        PlainTextWriter(source).write(destination, [TextSegment("1", "Replacement")])

    assert {path: path.read_bytes() for path in tmp_path.iterdir()} == before


def test_generator_failure_cleans_up_without_publishing(tmp_path):
    source = tmp_path / "source.txt"
    source.write_bytes(b"First\n\nSecond")

    def translations():
        yield TextSegment("1", "Erste")
        raise RuntimeError("Translation unavailable")

    with pytest.raises(RuntimeError, match="Translation unavailable"):
        PlainTextWriter(source).write(tmp_path / "translated.txt", translations())

    assert list(tmp_path.iterdir()) == [source]
    assert source.read_bytes() == b"First\n\nSecond"


@pytest.mark.parametrize("failure", ["missing_source", "decode", "encode", "publication"])
def test_io_and_encoding_failures_clean_up(tmp_path, monkeypatch, failure):
    source = tmp_path / "source.txt"
    if failure != "missing_source":
        source.write_bytes(b"\xff" if failure == "decode" else b"Original")
    before = {path: path.read_bytes() for path in tmp_path.iterdir()}

    def fail_link(*args, **kwargs):
        raise OSError("Hard links unavailable")

    if failure == "publication":
        monkeypatch.setattr(os, "link", fail_link)
    errors = {
        "missing_source": FileNotFoundError,
        "decode": UnicodeDecodeError,
        "encode": UnicodeEncodeError,
        "publication": OSError,
    }
    text = "\ud800" if failure == "encode" else "Translated"
    with pytest.raises(errors[failure]):
        PlainTextWriter(source).write(tmp_path / "translated.txt", [TextSegment("1", text)])

    assert {path: path.read_bytes() for path in tmp_path.iterdir()} == before


def test_destination_created_during_translation_is_preserved(tmp_path):
    source = tmp_path / "source.txt"
    source.write_bytes(b"Original")
    destination = tmp_path / "translated.txt"

    def translations():
        destination.write_bytes(b"Created by another process")
        yield TextSegment("1", "Translated")

    with pytest.raises(FileExistsError):
        PlainTextWriter(source).write(destination, translations())

    assert destination.read_bytes() == b"Created by another process"
    assert source.read_bytes() == b"Original"
    assert set(tmp_path.iterdir()) == {source, destination}
