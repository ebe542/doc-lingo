"""Exercise the local adapter without downloading models or importing Torch."""

import sys
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from doc_lingo import HuggingFaceBackend, TranslationError


@pytest.fixture
def runtime(monkeypatch):
    tokenizer = MagicMock()
    tokenizer.return_value.__getitem__.return_value.shape = (1, 10)
    tokenizer.return_value.to.return_value = {"input_ids": "fake-input"}
    tokenizer.decode.return_value = "Hallo Welt!"
    model = MagicMock()
    model.to.return_value = model
    model.config.max_position_embeddings = 32768
    model.generation_config.eos_token_id = 99
    tokens = model.generate.return_value.__getitem__.return_value
    tokens.__len__.return_value = 3
    tokens.__getitem__.return_value.item.return_value = 99
    torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: True),
        float16="float16",
        inference_mode=nullcontext,
    )
    transformers = SimpleNamespace(
        AutoTokenizer=SimpleNamespace(from_pretrained=MagicMock(return_value=tokenizer)),
        AutoModelForCausalLM=SimpleNamespace(from_pretrained=MagicMock(return_value=model)),
    )
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    return tokenizer, model, torch, transformers


def test_loads_lazily_once_and_translates(runtime):
    tokenizer, model, _, transformers = runtime
    backend = HuggingFaceBackend(local_files_only=True)
    transformers.AutoTokenizer.from_pretrained.assert_not_called()
    for _ in range(2):
        assert (
            backend.translate("Hello world!", source_lang="en", target_lang="de") == "Hallo Welt!"
        )
    transformers.AutoTokenizer.from_pretrained.assert_called_once()
    assert transformers.AutoTokenizer.from_pretrained.call_args.kwargs["local_files_only"]
    assert tokenizer.apply_chat_template.call_args.kwargs["enable_thinking"] is False
    assert model.generate.call_args.kwargs["do_sample"] is False


@pytest.mark.parametrize("case", ["input", "context", "unfinished", "empty", "generation", "load"])
def test_generation_failures_are_explicit_and_redacted(runtime, case):
    tokenizer, model, _, transformers = runtime
    backend = HuggingFaceBackend(max_input_tokens=5 if case == "input" else 2048)
    if case == "context":
        model.config.max_position_embeddings = 20
    elif case == "unfinished":
        model.generate.return_value.__getitem__.return_value.__len__.return_value = 0
    elif case == "empty":
        tokenizer.decode.return_value = " "
    elif case == "generation":
        model.generate.side_effect = RuntimeError("private source text")
    elif case == "load":
        transformers.AutoTokenizer.from_pretrained.side_effect = OSError("private source text")
    with pytest.raises(TranslationError) as error:
        backend.translate("Hello", source_lang="en", target_lang="de")
    assert "private source text" not in str(error.value)


def test_cuda_is_required(runtime):
    runtime[2].cuda.is_available = lambda: False
    with pytest.raises(TranslationError, match="CUDA is unavailable"):
        HuggingFaceBackend().translate("Hello", source_lang="en", target_lang="de")


def test_missing_dependencies(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", None)
    with pytest.raises(TranslationError, match="local dependency"):
        HuggingFaceBackend().translate("Hello", source_lang="en", target_lang="de")


def test_invalid_options_and_languages():
    with pytest.raises(ValueError):
        HuggingFaceBackend(max_new_tokens=0)
    with pytest.raises(TranslationError, match="language"):
        HuggingFaceBackend().translate("Hello", source_lang="xx", target_lang="de")


def test_no_model_needed_for_empty_or_same_language(runtime):
    backend = HuggingFaceBackend()
    assert backend.translate(" \n", source_lang="en", target_lang="de") == " \n"
    assert backend.translate("Hello", source_lang="en", target_lang="en") == "Hello"
    runtime[3].AutoTokenizer.from_pretrained.assert_not_called()


@pytest.mark.parametrize("preparation_error", [False, True])
def test_token_aware_splitting_uses_complete_inputs(runtime, preparation_error):
    tokenizer, model, _, _ = runtime
    tokenizer.apply_chat_template.side_effect = lambda messages, **kw: messages[-1]["content"]
    # Reserve output space: context, rather than max_input_tokens, is binding.
    model.config.max_position_embeddings = 24

    def tokenize(text, **kwargs):
        if preparation_error:
            raise ValueError("private tokenizer diagnostic")
        inputs = MagicMock()
        # Model-specific special/prompt overhead must count toward the limit.
        inputs.__getitem__.return_value.shape = (1, len(text) + 4)
        inputs.to.return_value = {"input_ids": text}
        return inputs

    tokenizer.side_effect = tokenize
    tokenizer.decode.side_effect = lambda *args, **kw: model.generate.call_args.kwargs[
        "input_ids"
    ].upper()
    backend = HuggingFaceBackend(max_input_tokens=24, max_new_tokens=8)
    if preparation_error:
        with pytest.raises(TranslationError) as error:
            backend.translate("First sentence. Next sentence.", source_lang="en", target_lang="de")
        assert "private tokenizer diagnostic" not in str(error.value)
        model.generate.assert_not_called()
    else:
        text = "First sentence. Next sentence."
        assert backend.translate(text, source_lang="en", target_lang="de") == text.upper()
        chunks = [call.kwargs["input_ids"] for call in model.generate.call_args_list]
        assert len(chunks) > 1
        assert " ".join(chunks) == text
        assert all(len(chunk) + 4 <= 16 for chunk in chunks)
