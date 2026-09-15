"""Check list segmentation and format retention through the public adapters."""

import pytest

from doc_lingo import PlainTextReader, PlainTextWriter, TextSegment, translate_document


@pytest.mark.parametrize("prefix", ["- ", "* ", "• ", "1. ", "12) ", "  -   ", "\t2)\t"])
def test_list_prefix_is_not_sent_to_translation(tmp_path, prefix):
    source = tmp_path / "source.txt"
    destination = tmp_path / "output.txt"
    original = f"\ufeffIntroduction\r\n{prefix}First\r\n{prefix}Second\r\n\nEnd"
    source.write_bytes(original.encode())
    calls = []

    class Backend:
        def translate(self, text, *, source_lang, target_lang):
            calls.append(text)
            return text.replace("First", "Erste").replace("Second", "Zweite")

    translate_document(
        PlainTextReader(source),
        PlainTextWriter(source),
        Backend(),
        destination,
        source_lang="en",
        target_lang="de",
    )
    assert calls == ["Introduction\r\n", "First\r\n", "Second\r\n", "End"]
    assert (
        destination.read_bytes()
        == original.replace("First", "Erste").replace("Second", "Zweite").encode()
    )
    assert source.read_bytes() == original.encode()


@pytest.mark.parametrize("content", ["-word\n*word\n1.5 units", "- \n*\n1) ", "Plain\ntext"])
def test_marker_like_prose_stays_one_paragraph(tmp_path, content):
    source = tmp_path / "source.txt"
    source.write_bytes(content.encode())
    with PlainTextReader(source).iter_segments() as segments:
        assert list(segments) == [TextSegment("1", content)]


@pytest.mark.parametrize("content", ["  - First\n\t* Second\n", "1. First\r\n2) Second", "• Last"])
def test_lists_roundtrip_with_stable_ids(tmp_path, content):
    source = tmp_path / "source.txt"
    destination = tmp_path / "output.txt"
    source.write_bytes(content.encode())
    reader = PlainTextReader(source)
    with reader.iter_segments() as segments:
        first = list(segments)
    with reader.iter_segments() as segments:
        assert list(segments) == first
    assert [segment.id for segment in first] == [str(i + 1) for i in range(len(first))]
    PlainTextWriter(source).write(destination, iter(first))
    assert destination.read_bytes() == content.encode()


@pytest.mark.parametrize(
    ("prefix", "segment_type"),
    [
        ("- ", "bullet_item"),
        ("* ", "bullet_item"),
        ("• ", "bullet_item"),
        ("1. ", "numbered_item"),
        ("12) ", "numbered_item"),
        ("\t2)\t", "numbered_item"),
    ],
)
def test_types_reach_writer_and_progress(tmp_path, prefix, segment_type):
    source = tmp_path / "source.txt"
    source.write_bytes(f"Intro\n{prefix}Item\n\nEnd".encode())
    reader = PlainTextReader(source)
    with reader.iter_segments() as segments:
        extracted = list(segments)
    assert [segment.type for segment in extracted] == ["paragraph", segment_type, "paragraph"]
    written = []
    progress = []

    class Backend:
        def translate(self, text, *, source_lang, target_lang):
            return text.upper()

    class Writer:
        def write(self, destination, translations):
            written.extend(translations)

    translate_document(
        reader,
        Writer(),
        Backend(),
        tmp_path / "unused.txt",
        source_lang="en",
        target_lang="de",
        on_progress=lambda count, kind: progress.append((count, kind)),
    )
    assert [(segment.id, segment.type) for segment in written] == [
        (segment.id, segment.type) for segment in extracted
    ]
    assert [segment.text for segment in written] == [segment.text.upper() for segment in extracted]
    assert progress == [(1, "paragraph"), (2, segment_type), (3, "paragraph")]
