"""Test Marian behavior without installing models or requiring a GPU."""

import sys
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from doc_lingo import HuggingFaceBackend, MarianBackend, TranslationError
from scripts.evaluate_translation_quality import runtime_metadata


@pytest.fixture
def runtime(monkeypatch):
    tokenizer = MagicMock()
    tokenizer.eos_token_id = 0
    tokenizer.return_value.__getitem__.return_value.shape = (1, 12)
    tokenizer.return_value.to.return_value = {"input_ids": "source-tokens"}
    tokenizer.decode.return_value = "Das Dokument enthält zwei Absätze."
    model = MagicMock()
    model.to.return_value = model
    tokens = model.generate.return_value.__getitem__.return_value
    tokens.__len__.return_value = 8
    tokens.__getitem__.return_value.item.return_value = 0
    torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: True, get_device_name=lambda _: "test GPU"),
        version=SimpleNamespace(cuda="13.2"),
        float32="float32",
        inference_mode=nullcontext,
    )
    transformers = SimpleNamespace(
        MarianTokenizer=SimpleNamespace(from_pretrained=MagicMock(return_value=tokenizer)),
        AutoModelForSeq2SeqLM=SimpleNamespace(from_pretrained=MagicMock(return_value=model)),
    )
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    return tokenizer, model, torch, transformers


def test_translation_has_no_chat_prompt_and_reuses_loaded_model(runtime):
    tokenizer, model, _, transformers = runtime
    backend = MarianBackend(local_files_only=True)
    transformers.MarianTokenizer.from_pretrained.assert_not_called()
    for _ in range(2):
        assert backend.translate("Source", source_lang="en", target_lang="de").startswith("Das")
    transformers.MarianTokenizer.from_pretrained.assert_called_once_with(
        backend.model_name, revision=backend.revision, local_files_only=True
    )
    tokenizer.assert_called_with("Source", return_tensors="pt", truncation=False)
    tokenizer.apply_chat_template.assert_not_called()
    assert model.generate.call_args.kwargs["num_beams"] == 4
    assert model.generate.call_args.kwargs["forced_eos_token_id"] is None
    assert tokenizer.decode.call_args.args[0] is model.generate.return_value[0]


@pytest.mark.parametrize("case", ["input", "unfinished", "empty", "generate", "load", "cuda"])
def test_expected_failures(runtime, case):
    tokenizer, model, torch, transformers = runtime
    backend = MarianBackend(max_input_tokens=5 if case == "input" else 512)
    if case == "unfinished":
        tokens = model.generate.return_value.__getitem__.return_value
        tokens.__getitem__.return_value.item.return_value = 7
    elif case == "empty":
        tokenizer.decode.return_value = " "
    elif case == "generate":
        model.generate.side_effect = RuntimeError("private diagnostic")
    elif case == "load":
        transformers.MarianTokenizer.from_pretrained.side_effect = OSError("private diagnostic")
    elif case == "cuda":
        torch.cuda.is_available = lambda: False
    with pytest.raises(TranslationError) as error:
        backend.translate("Source", source_lang="en", target_lang="de")
    assert "private diagnostic" not in str(error.value)
    if case == "input":
        model.generate.assert_not_called()


def test_missing_dependencies(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", None)
    with pytest.raises(TranslationError, match="local extra"):
        MarianBackend().translate("Source", source_lang="en", target_lang="de")


@pytest.mark.parametrize(
    "options", [{"max_input_tokens": 513}, {"max_new_tokens": 512}, {"max_new_tokens": 0}]
)
def test_invalid_limits(options):
    with pytest.raises(ValueError):
        MarianBackend(**options)


def test_language_validation_and_empty_input(runtime):
    backend = MarianBackend()
    with pytest.raises(TranslationError, match="only en to de"):
        backend.translate("Hallo", source_lang="de", target_lang="en")
    assert backend.translate(" \n", source_lang="en", target_lang="de") == " \n"
    runtime[3].MarianTokenizer.from_pretrained.assert_not_called()


def test_marian_report_metadata_does_not_claim_chat_prompts(runtime):
    metadata = runtime_metadata(MarianBackend())
    assert metadata["backend"] == "marian"
    assert metadata["prompts"] == []
    assert metadata["prompt_mode"] == "none"
    assert metadata["dtype"] == "float32"
    assert metadata["generation"]["num_beams"] == 4


def test_qwen_metadata_keeps_prompt_identities(runtime):
    metadata = runtime_metadata(HuggingFaceBackend())
    assert metadata["backend"] == "qwen"
    assert metadata["prompt_mode"] == "chat"
    assert metadata["dtype"] == "float16"
    assert len(metadata["prompts"]) == 2


@pytest.mark.parametrize("preparation_error", [False, True])
def test_token_aware_splitting_uses_complete_inputs(runtime, preparation_error):
    tokenizer, model, _, _ = runtime

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
    backend = MarianBackend(max_input_tokens=24, max_new_tokens=8)
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
        assert all(len(chunk) + 4 <= 24 for chunk in chunks)
