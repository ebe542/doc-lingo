"""Verify lazy orchestration and cleanup without models or network access."""

from contextlib import contextmanager

import pytest

from doc_lingo import (
    PlainTextReader,
    PlainTextWriter,
    TextSegment,
    TranslationError,
    translate_document,
)


class RecordingBackend:
    def __init__(self):
        self.calls = []

    def translate(self, text, *, source_lang, target_lang):
        self.calls.append((text, source_lang, target_lang))
        return text.upper()


@pytest.mark.parametrize("stop_early", [False, True])
def test_lazy_translation_preserves_ids_and_session_lifetime(tmp_path, stop_early):
    backend = RecordingBackend()
    active = False
    captured = []

    class Reader:
        @contextmanager
        def iter_segments(self):
            nonlocal active
            active = True
            try:
                yield iter([TextSegment("slide:7", "hello"), TextSegment("slide:9", "world")])
            finally:
                active = False

    class Writer:
        def write(self, destination, translations):
            assert destination == tmp_path / "result.txt"
            assert active
            assert backend.calls == []
            captured.append(translations)
            assert next(translations) == TextSegment("slide:7", "HELLO")
            assert backend.calls == [("hello", "en", "de")]
            if not stop_early:
                assert next(translations) == TextSegment("slide:9", "WORLD")
                assert list(translations) == []
            assert active

    translate_document(
        Reader(), Writer(), backend, tmp_path / "result.txt", source_lang="en", target_lang="de"
    )

    assert not active
    assert list(captured[0]) == []
    expected = [("hello", "en", "de")]
    if not stop_early:
        expected.append(("world", "en", "de"))
    assert backend.calls == expected


@pytest.mark.parametrize("origin", ["reader", "backend", "writer"])
def test_errors_propagate_unchanged_and_reader_closes(tmp_path, origin):
    failure = TranslationError("Backend unavailable") if origin == "backend" else OSError("Failure")
    closed = False
    captured = []

    class Reader:
        @contextmanager
        def iter_segments(self):
            nonlocal closed
            try:
                if origin == "reader":
                    raise failure
                yield iter([TextSegment("1", "hello")])
            finally:
                closed = True

    class Backend:
        def translate(self, text, *, source_lang, target_lang):
            raise failure

    class Writer:
        def write(self, destination, translations):
            captured.append(translations)
            if origin == "writer":
                raise failure
            list(translations)

    with pytest.raises(type(failure)) as error:
        translate_document(
            Reader(),
            Writer(),
            Backend(),
            tmp_path / "result.txt",
            source_lang="en",
            target_lang="de",
        )

    assert error.value is failure
    assert closed
    for translations in captured:
        assert list(translations) == []


@pytest.mark.parametrize("content", ["", "\ufeff\r\n \t\n", "\ufeffHello\r\n\r\nWorld"])
def test_txt_service_writes_translations_and_preserves_structure(tmp_path, content):
    source = tmp_path / "source.txt"
    destination = tmp_path / "result.txt"
    source.write_bytes(content.encode())
    backend = RecordingBackend()

    translate_document(
        PlainTextReader(source),
        PlainTextWriter(source),
        backend,
        destination,
        source_lang="en",
        target_lang="de",
    )

    assert destination.read_bytes() == content.upper().encode()
    assert source.read_bytes() == content.encode()
    assert set(tmp_path.iterdir()) == {source, destination}
    assert len(backend.calls) == (2 if "Hello" in content else 0)


def test_backend_failure_after_first_paragraph_leaves_no_output(tmp_path):
    source = tmp_path / "source.txt"
    source.write_bytes(b"First\n\nSecond")
    failure = TranslationError("Translation interrupted")

    class Backend:
        def translate(self, text, *, source_lang, target_lang):
            if text == "Second":
                raise failure
            return "Erste"

    with pytest.raises(TranslationError) as error:
        translate_document(
            PlainTextReader(source),
            PlainTextWriter(source),
            Backend(),
            tmp_path / "result.txt",
            source_lang="en",
            target_lang="de",
        )

    assert error.value is failure
    assert source.read_bytes() == b"First\n\nSecond"
    assert list(tmp_path.iterdir()) == [source]
