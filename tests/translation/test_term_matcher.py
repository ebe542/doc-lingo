"""Check matching boundaries and sentence capitalization without model inference."""

import re

import pytest

from doc_lingo import Glossary, GlossaryBackend, GlossaryEntry
from doc_lingo.translation.term_matcher import TermMatcher


def test_leftmost_longest_and_boundaries():
    matcher = TermMatcher(["learning", "machine learning", "RAG", "C++"])
    text = "unlearning _RAG RAG2 Machine Learning, RAG; C++."
    assert [(text[a:b], i) for a, b, i in matcher.finditer(text)] == [
        ("Machine Learning", 1),
        ("RAG", 2),
        ("C++", 3),
    ]


def test_shared_prefix_and_longer_failed_boundary():
    assert list(TermMatcher(["cat", "cat dog"]).finditer("cat dogs")) == [(0, 3, 0)]


def test_original_offsets_survive_unicode_case_handling():
    matcher = TermMatcher(["Straße", "index", "kernel", "signal"])
    text = "STRAẞE İndex Kernel ſignal STRASSE"
    assert [text[a:b] for a, b, _ in matcher.finditer(text)] == [
        "STRAẞE",
        "İndex",
        "Kernel",
        "ſignal",
    ]


@pytest.mark.parametrize("terms", [[""], ["Index", "ındex"], ["K", "K"]])
def test_ambiguous_or_empty_entries_are_rejected(terms):
    with pytest.raises(ValueError):
        TermMatcher(terms)


class Echo:
    def translate(self, text, **kwargs):
        return text


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Learning happens.", "Lernen happens."),
        ("“learning” happens.", "“Lernen” happens."),
        ("Done! learning happens.", "Done! Lernen happens."),
        ("We use\nlearning here.", "We use\nlernen here."),
        ("We use learning here.", "We use lernen here."),
    ],
)
def test_sentence_initial_replacement_case(text, expected):
    backend = GlossaryBackend(
        Echo(), Glossary("en", "de", (GlossaryEntry("learning", "translate", "lernen"),))
    )
    assert backend.translate(text, source_lang="en", target_lang="de") == expected


def test_keep_mode_never_changes_original_case():
    backend = GlossaryBackend(Echo(), Glossary("en", "de", (GlossaryEntry("iPhone", "keep"),)))
    assert backend.translate("iPhone works.", source_lang="en", target_lang="de") == "iPhone works."


def test_capitalization_follows_translated_position():
    class Reordered:
        def translate(self, text, **kwargs):
            marker = re.search(r"DLG[A-F0-9]+X0Z", text).group()
            return marker + " hilft."

    backend = GlossaryBackend(
        Reordered(), Glossary("en", "de", (GlossaryEntry("learning", "annotate", "lernen"),))
    )
    assert backend.translate("We use learning.", source_lang="en", target_lang="de") == (
        "Lernen (learning) hilft."
    )
