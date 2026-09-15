"""Check progress counts and failure cleanup through real TXT adapters."""

import pytest

from doc_lingo import PlainTextReader, PlainTextWriter, TranslationError, translate_document


@pytest.mark.parametrize("content", ["", "First\n\nSecond"])
def test_progress_follows_successful_backend_calls(tmp_path, content):
    source = tmp_path / "source.txt"
    source.write_text(content, encoding="utf-8")
    events = []

    class Backend:
        def translate(self, text, *, source_lang, target_lang):
            events.append("translated")
            return text

    translate_document(
        PlainTextReader(source),
        PlainTextWriter(source),
        Backend(),
        tmp_path / "output.txt",
        source_lang="en",
        target_lang="de",
        on_progress=lambda count, segment_type: events.append((count, segment_type)),
    )
    assert events == (
        ["translated", (1, "paragraph"), "translated", (2, "paragraph")] if content else []
    )


@pytest.mark.parametrize("callback_failure", [False, True])
def test_failures_do_not_publish_output(tmp_path, callback_failure):
    source = tmp_path / "source.txt"
    source.write_bytes(b"First\n\nSecond")
    progress = []

    class Backend:
        def translate(self, text, *, source_lang, target_lang):
            if text == "Second":
                raise TranslationError("Failed")
            return text

    def report(count, segment_type):
        progress.append((count, segment_type))
        if callback_failure:
            raise RuntimeError("Progress callback failed")

    with pytest.raises(RuntimeError if callback_failure else TranslationError):
        translate_document(
            PlainTextReader(source),
            PlainTextWriter(source),
            Backend(),
            tmp_path / "output.txt",
            source_lang="en",
            target_lang="de",
            on_progress=report,
        )
    assert progress == [(1, "paragraph")]
    assert list(tmp_path.iterdir()) == [source]
