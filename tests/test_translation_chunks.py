"""Check lossless source boundaries and fail-closed chunk translation offline."""

import pytest

from doc_lingo import PlainTextReader, PlainTextWriter, TranslationError, translate_document
from doc_lingo.translation.chunks import split_text, translate_chunks


@pytest.mark.parametrize(
    "text,limit",
    [
        ("Short sentence.", 50),
        ("First sentence. Second sentence! Third sentence?", 20),
        ("one two three four five six", 10),
        ("eins\r\n  zwei\t drei vier", 8),
        ("Grüße 世界. Noch ein Satz.", 12),
        ('He said "Hello!" Then left.', 18),
        ("third\r\n", 6),
        ("  third\r\n", 6),
        (" \t\r\n", 1),
    ],
)
def test_chunks_fit_and_reconstruct_source_exactly(text, limit):
    chunks = list(split_text(text, lambda part: len(part) <= limit))
    assert all(len(part) <= limit for part, _ in chunks)
    assert "".join(part + separator for part, separator in chunks) == text


def test_sentence_boundary_precedes_nearer_word_boundary():
    text = "One. This is a longer sentence."
    chunks = list(split_text(text, lambda part: len(part) <= 26))
    assert chunks == [("One.", " "), ("This is a longer sentence.", "")]


def test_unbroken_word_is_not_truncated():
    with pytest.raises(TranslationError, match="word exceeds"):
        list(split_text("abcdefghijk", lambda part: len(part) <= 5))


def test_no_partial_result_on_later_generation_failure():
    calls = []

    def translate(part):
        calls.append(part)
        if len(calls) == 2:
            raise TranslationError("Unfinished output")
        return part.upper()

    with pytest.raises(TranslationError, match="Unfinished"):
        translate_chunks("first second", lambda part: len(part) <= 6, translate)
    assert calls == ["first", "second"]


@pytest.mark.parametrize("fail", [False, True])
def test_document_keeps_one_list_segment_and_atomic_output(tmp_path, fail):
    source = tmp_path / "source.txt"
    original = b"- first second third\r\n"
    source.write_bytes(original)
    output = tmp_path / "out.txt"
    progress = []

    class Backend:
        def translate(self, text, **languages):
            def generate(part):
                if fail and part == "third":
                    raise TranslationError("Unfinished output")
                return part.upper()

            return translate_chunks(text, lambda part: len(part) <= 6, generate)

    def run():
        translate_document(
            PlainTextReader(source),
            PlainTextWriter(source),
            Backend(),
            output,
            source_lang="en",
            target_lang="de",
            on_progress=lambda count, kind: progress.append((count, kind)),
        )

    if fail:
        with pytest.raises(TranslationError, match="Unfinished output"):
            run()
        assert not output.exists()
        assert progress == []
        assert list(tmp_path.iterdir()) == [source]
    else:
        run()
        assert output.read_bytes() == b"- FIRST SECOND THIRD\r\n"
        assert progress == [(1, "bullet_item")]
    assert source.read_bytes() == original


def test_outer_whitespace_does_not_reach_generator_when_splitting():
    calls = []

    def generate(part):
        calls.append(part)
        return part.upper()

    result = translate_chunks("  third\r\n", lambda part: len(part) <= 6, generate)
    assert result == "  THIRD\r\n"
    assert calls == ["third"]


def test_sentences_are_translated_individually_even_when_paragraph_fits():
    calls = []

    def translate(part):
        calls.append(part)
        return part.upper()

    text = "First sentence. Second sentence!"
    assert translate_chunks(text, lambda part: True, translate) == text.upper()
    assert calls == ["First sentence.", "Second sentence!"]
