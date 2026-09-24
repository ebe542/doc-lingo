"""Format-independent protected ranges and scoped failure reporting."""

import re

import pytest

from doc_lingo import RecoverableTranslationError, TextSegment, TranslationError
from doc_lingo.translation.issues import issue_sink
from doc_lingo.translation.protected import translate_segment


class Backend:
    def __init__(self, transform):
        self.transform = transform

    def translate(self, text, **kwargs):
        return self.transform(text)


def translate(segment, transform):
    return translate_segment(segment, Backend(transform), source_lang="en", target_lang="de")


def test_outer_syntax_is_not_sent_to_model():
    segment = TextSegment("1", "# Hello\n", protected_spans=((0, 2), (7, 8)))

    def transform(text):
        assert text == "Hello"
        return "Hallo"

    assert translate(segment, transform) == "# Hallo\n"


def test_fully_protected_text_needs_no_model():
    segment = TextSegment("1", "code", protected_spans=((0, 4),))
    assert translate(segment, lambda text: pytest.fail("Model called")) == "code"


@pytest.mark.parametrize("failure", ["exception", "empty", "extra", "partial"])
def test_failed_markers_are_strict_by_default(failure):
    segment = TextSegment("1", "Hello `code` world", protected_spans=((6, 12),))

    def transform(text):
        if failure == "exception":
            raise RecoverableTranslationError("Generation failed")
        marker = re.search(r"DLM[0-9A-F]+X0Z", text)
        assert marker is not None
        if failure == "empty":
            return marker.group()
        if failure == "extra":
            return text + marker.group().replace("X0Z", "X99Z")
        return text + marker.group().split("X")[0]

    with pytest.raises(RecoverableTranslationError, match="syntax protection"):
        translate(segment, transform)
    assert issue_sink.get() is None


def test_fatal_errors_propagate_and_restore_context():
    segment = TextSegment("1", "Hello `code` world", protected_spans=((6, 12),))

    def fail(text):
        raise TranslationError("Loading failed")

    with pytest.raises(TranslationError, match="Loading failed"):
        translate(segment, fail)
    assert issue_sink.get() is None
