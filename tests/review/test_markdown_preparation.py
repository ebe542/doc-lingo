"""Markdown review preparation shares content protection, not formatting markers."""

import re

import pytest

from doc_lingo.review import ReviewJobError, translate_markdown_job
from doc_lingo.translation.issues import RecoverableTranslationError, issue_sink, retain_original
from doc_lingo.translation.protocols import TranslationError


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source.md"
    path.write_text(
        "Call `predict()` before **saving** with `save()`.\n", encoding="utf-8", newline="\n"
    )
    return path


def test_only_content_markers_reach_backend_and_may_move(source):
    calls = []

    class Backend:
        def translate(self, text, **languages):
            calls.append((text, languages))
            markers = re.findall(r"\bDLM\w*X\d+Z\b", text)
            assert len(markers) == 2
            assert "**" not in text and "`" not in text
            assert "predict()" not in text and "save()" not in text
            return f"Vor {markers[1]} bitte {markers[0]} aufrufen."

    progress = []
    job = translate_markdown_job(
        source,
        Backend(),
        source_lang="en",
        target_lang="de",
        on_progress=lambda *args: progress.append(args),
    )
    assert job.blocks[0].proposal == "Vor save() bitte predict() aufrufen."
    assert job.blocks[0].original == "Call predict() before saving with save()."
    assert calls[0][1] == {"source_lang": "en", "target_lang": "de"}
    assert progress == [(1, "paragraph")]
    assert job.source == source.read_bytes()
    assert issue_sink.get() is None


@pytest.mark.parametrize("mode", ["missing", "empty", "recovery", "raised", "ambiguous"])
def test_recoverable_failures_retain_plain_block(source, mode):
    class Backend:
        def translate(self, text, **kwargs):
            if mode == "recovery":
                return retain_original(text, "cannot translate")
            if mode == "raised":
                raise RecoverableTranslationError("cannot translate")
            if mode == "empty":
                return " "
            if mode == "ambiguous":
                return text + " predict()"
            return "All code was lost."

    issues = []
    job = translate_markdown_job(
        source, Backend(), source_lang="en", target_lang="de", on_issue=issues.append
    )
    assert job.blocks[0].proposal == job.blocks[0].original
    assert len(issues) == 1
    assert issues[0].original == job.blocks[0].original
    assert issues[0].segment_id == "1"
    assert issues[0].action == "retained_original"
    assert issue_sink.get() is None
    with pytest.raises(RecoverableTranslationError):
        translate_markdown_job(source, Backend(), source_lang="en", target_lang="de")
    assert issue_sink.get() is None


def test_source_mutation_is_detected(source):
    class Backend:
        def translate(self, text, **kwargs):
            source.write_bytes(b"changed")
            return text

    with pytest.raises(ReviewJobError, match="changed"):
        translate_markdown_job(source, Backend(), source_lang="en", target_lang="de")


def test_fatal_backend_or_callback_failure_resets_context(source):
    class Backend:
        def translate(self, text, **kwargs):
            raise TranslationError("fatal")

    with pytest.raises(TranslationError, match="fatal"):
        translate_markdown_job(source, Backend(), source_lang="en", target_lang="de")
    assert issue_sink.get() is None

    class Recovery:
        def translate(self, text, **kwargs):
            return retain_original(text, "failed")

    def fail(issue):
        raise OSError("callback failed")

    with pytest.raises(OSError, match="callback failed"):
        translate_markdown_job(
            source, Recovery(), source_lang="en", target_lang="de", on_issue=fail
        )
    assert issue_sink.get() is None


def test_empty_source_needs_no_backend(tmp_path):
    source = tmp_path / "empty.md"
    source.write_bytes(b"")

    class Forbidden:
        def translate(self, *args, **kwargs):
            pytest.fail("Empty document must bypass backend")

    assert (
        translate_markdown_job(source, Forbidden(), source_lang="en", target_lang="de").blocks == ()
    )
