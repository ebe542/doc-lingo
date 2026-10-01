"""Exercise the adapter offline with a tokenizer/engine double."""

import sys
from types import SimpleNamespace

import pytest

from doc_lingo.translation.alignment import AlignmentError
from doc_lingo.translation.simalign_adapter import SimAlignAdapter


class Tokenizer:
    model_max_length = 512

    def __call__(self, words, **kwargs):
        assert kwargs["truncation"] is False
        return {"input_ids": list(range(len(words) + 2))}

    def tokenize(self, word):
        return [word]

    def num_special_tokens_to_add(self, **kwargs):
        return 2


def engine(pairs=()):
    return SimpleNamespace(
        embed_loader=SimpleNamespace(
            tokenizer=Tokenizer(),
            emb_model=SimpleNamespace(config=SimpleNamespace(max_position_embeddings=512)),
        ),
        get_word_aligns=lambda *args: {"inter": pairs, "itermax": pairs},
    )


def test_many_to_many_components_keep_offsets():
    result = SimAlignAdapter(engine([(0, 0), (1, 0), (1, 1)])).align("ä a!", "A B")
    assert len(result.links) == 1
    assert [(r.start, r.end) for r in result.links[0].source_ranges] == [(0, 1), (2, 3)]
    assert result.unaligned[0].start == 3


@pytest.mark.parametrize("source,target", [("", "text"), ("word", ""), (" ", "")])
def test_empty_side_needs_no_inference(source, target):
    assert SimAlignAdapter(None).align(source, target).source == source


def test_length_checked_before_engine_call():
    fake = engine()
    fake.embed_loader.tokenizer.model_max_length = 2
    with pytest.raises(AlignmentError, match="token limit"):
        SimAlignAdapter(fake).align("word", "Wort")


@pytest.mark.parametrize("pieces,message", [([], "dropped"), (["a", "b"], "inconsistent")])
def test_tokenizer_mapping_errors(pieces, message):
    fake = engine()
    fake.embed_loader.tokenizer.tokenize = lambda word: pieces
    with pytest.raises(AlignmentError, match=message):
        SimAlignAdapter(fake).align("word", "Wort")


def test_invalid_indices():
    with pytest.raises(AlignmentError, match="invalid word index"):
        SimAlignAdapter(engine([(1, 0)])).align("word", "Wort")


def test_no_edges_are_unaligned():
    assert len(SimAlignAdapter(engine()).align("one two", "eins").unaligned) == 2


def test_reordered_components():
    result = SimAlignAdapter(engine([(0, 1), (1, 0)])).align("a b", "B A")
    assert result.links[0].target_ranges[0].start == 2


def test_invalid_method():
    with pytest.raises(ValueError):
        SimAlignAdapter(None, method="unknown")


def test_execution_error_is_sanitized():
    fake = engine()

    def fail(*args):
        raise RuntimeError("private content")

    fake.get_word_aligns = fail
    with pytest.raises(AlignmentError, match="^SimAlign execution failed$"):
        SimAlignAdapter(fake).align("word", "Wort")


def test_optional_loading(monkeypatch):
    fake = engine()
    monkeypatch.setitem(sys.modules, "simalign", SimpleNamespace(SentenceAligner=lambda **kw: fake))
    assert SimAlignAdapter.load("snapshot").engine is fake


def test_optional_loading_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "simalign", None)
    with pytest.raises(AlignmentError, match="Could not load"):
        SimAlignAdapter.load("snapshot")
