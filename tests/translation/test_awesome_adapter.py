"""Offline awesome-align boundary and restoration checks."""

import sys
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from doc_lingo.translation.alignment import AlignmentError
from doc_lingo.translation.awesome_adapter import AwesomeAlignAdapter


class Tokenizer:
    max_len = 512
    pad_token_id, cls_token_id, sep_token_id = 0, 101, 102

    def tokenize(self, word):
        return [word]

    def convert_tokens_to_ids(self, words):
        return list(range(len(words)))

    def num_added_tokens(self, **kwargs):
        return 2

    def prepare_for_model(self, ids, **kwargs):
        return {"input_ids": [[101, *ids, 102]]}


def make_adapter():
    model = SimpleNamespace(
        config=SimpleNamespace(max_position_embeddings=512),
        get_aligned_word=lambda *args, **kw: [{(0, 0)}],
    )
    return AwesomeAlignAdapter(model, Tokenizer())


@pytest.fixture
def upstream(monkeypatch):
    modeling = SimpleNamespace(PAD_ID=9)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(no_grad=nullcontext))
    monkeypatch.setitem(sys.modules, "awesome_align", SimpleNamespace(modeling=modeling))
    return modeling


def test_alignment_and_global_restoration(upstream):
    result = make_adapter().align("ä!", "A!")
    assert result.links[0].source_ranges[0].end == 1
    assert result.unaligned[0].start == 1
    assert vars(upstream) == {"PAD_ID": 9}


def test_expected_execution_failure(upstream):
    adapter = make_adapter()

    def fail(*args, **kwargs):
        raise RuntimeError("private data")

    adapter.model.get_aligned_word = fail
    with pytest.raises(AlignmentError, match="^awesome-align execution failed$"):
        adapter.align("word", "Wort")
    assert vars(upstream) == {"PAD_ID": 9}


def test_empty_target():
    assert make_adapter().align("word", "").unaligned[0].end == 4


def test_token_budget():
    adapter = make_adapter()
    adapter.tokenizer.max_len = 2
    with pytest.raises(AlignmentError, match="token limit"):
        adapter._encode(["word"])


def test_dropped_word():
    adapter = make_adapter()
    adapter.tokenizer.tokenize = lambda word: []
    with pytest.raises(AlignmentError, match="dropped"):
        adapter._encode(["word"])


def test_installed_tokenizer_api_without_model_download(tmp_path):
    module = pytest.importorskip("awesome_align.tokenization_bert")
    vocab = tmp_path / "vocab.txt"
    vocab.write_text("[PAD]\n[UNK]\n[CLS]\n[SEP]\n[MASK]\nword\n", encoding="utf-8")
    tokenizer = module.BertTokenizer(str(vocab), do_lower_case=False)
    adapter = make_adapter()
    adapter.tokenizer = tokenizer
    encoded, mapping = adapter._encode(["word"])
    assert encoded.tolist() == [[tokenizer.cls_token_id, 5, tokenizer.sep_token_id]]
    assert mapping == [0]
    adapter.model.config.max_position_embeddings = 2
    with pytest.raises(AlignmentError, match="token limit"):
        adapter._encode(["word"])


def test_load_optional_modules(monkeypatch):
    adapter = make_adapter()
    adapter.model.to = lambda device: None
    adapter.model.eval = lambda: None
    monkeypatch.setitem(
        sys.modules,
        "awesome_align.modeling",
        SimpleNamespace(
            BertForMaskedLM=SimpleNamespace(from_pretrained=lambda path: adapter.model)
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "awesome_align.tokenization_bert",
        SimpleNamespace(
            BertTokenizer=SimpleNamespace(from_pretrained=lambda path: adapter.tokenizer)
        ),
    )
    assert AwesomeAlignAdapter.load("snapshot").model is adapter.model


def test_load_failure(monkeypatch):
    monkeypatch.setitem(sys.modules, "awesome_align.modeling", None)
    with pytest.raises(AlignmentError, match="Could not load"):
        AwesomeAlignAdapter.load("snapshot")
