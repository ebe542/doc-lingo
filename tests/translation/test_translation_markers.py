"""Stable backend input and collision-safe restoration for both protection layers."""

import pytest

from doc_lingo import Glossary, GlossaryBackend, GlossaryEntry, TextSegment
from doc_lingo.translation.markers import MARKER_POLICY, marker_prefix
from doc_lingo.translation.protected import translate_segment


class RecordingBackend:
    def __init__(self):
        self.calls = []

    def translate(self, text, **kwargs):
        self.calls.append(text)
        return text


@pytest.mark.parametrize("namespace", ["DLM", "DLG"])
def test_prefix_is_stable_and_skips_existing_prefixes(namespace):
    first = marker_prefix("", namespace=namespace)
    second = marker_prefix(first, namespace=namespace)
    source = f"literal {first}X0Z and {second.lower()}unfinished"
    third = marker_prefix(source, namespace=namespace)
    assert third not in (first, second)
    assert third.lower() not in source.lower()
    assert marker_prefix("unrelated", namespace=namespace) == first
    assert marker_prefix(source, namespace=namespace) == third
    assert len(first) == len(namespace) + 32
    assert len(set(first[len(namespace) :])) > 1
    assert "0" * 8 not in first
    assert MARKER_POLICY == "deterministic-prefix-v2"


@pytest.mark.parametrize("with_glossary", [False, True])
@pytest.mark.parametrize("collision", [False, True])
def test_document_and_glossary_inputs_repeat_and_literals_roundtrip(with_glossary, collision):
    document_prefix = marker_prefix("", namespace="DLM")
    glossary_prefix = marker_prefix("", namespace="DLG")
    literals = f"{document_prefix}X0Z {glossary_prefix}X0Z " if collision else ""
    source = literals + "Hello **world** again."
    start = source.index("**")
    end = source.index("**", start + 2)
    segment = TextSegment("1", source, protected_spans=((start, start + 2), (end, end + 2)))
    backend = RecordingBackend()
    glossary = Glossary("en", "de", (GlossaryEntry("world", "keep"),))

    def run():
        translator = GlossaryBackend(backend, glossary) if with_glossary else backend
        return translate_segment(segment, translator, source_lang="en", target_lang="de")

    assert run() == source
    first_input = backend.calls[-1]
    translate_segment(
        TextSegment("other", "Unrelated"), backend, source_lang="en", target_lang="de"
    )
    assert run() == source
    assert backend.calls[-1] == first_input
    assert marker_prefix(source, namespace="DLM") + "X0Z" in first_input
    if with_glossary:
        assert marker_prefix(source, namespace="DLG") + "X0Z" in first_input
    if collision:
        assert first_input.startswith(literals)


def test_glossary_translation_uses_stable_markers_and_restores_target():
    backend = RecordingBackend()
    glossary = Glossary("en", "de", (GlossaryEntry("world", "translate", "Welt"),))
    for _ in range(2):
        translator = GlossaryBackend(backend, glossary)
        assert (
            translator.translate("Hello world.", source_lang="en", target_lang="de")
            == "Hello Welt."
        )
    assert backend.calls[0] == backend.calls[1]
