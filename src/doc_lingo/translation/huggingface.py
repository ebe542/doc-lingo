"""Lazy local Qwen translation on CUDA; no hosted inference calls."""

from typing import Any

from doc_lingo.translation.prompts import translation_messages
from doc_lingo.translation.protocols import TranslationError

DEFAULT_MODEL = "Qwen/Qwen3-1.7B"
DEFAULT_REVISION = "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"


class HuggingFaceBackend:
    """Load once on first use; require CUDA and keep model state caller-owned.

    Initial scope is en/de translation with Qwen3-compatible chat templates.
    No automatic CPU fallback, quantization, retries, or paragraph splitting.
    Model downloads may occur unless local_files_only is enabled. Hugging Face
    resolves authentication from its standard environment/cache, never from .env.
    """

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        revision: str = DEFAULT_REVISION,
        max_input_tokens: int = 2048,
        max_new_tokens: int = 1024,
        local_files_only: bool = False,
    ) -> None:
        if max_input_tokens < 1 or max_new_tokens < 1:
            raise ValueError("Token limits must be positive")
        self.model_name = model
        self.revision = revision
        self.max_input_tokens = max_input_tokens
        self.max_new_tokens = max_new_tokens
        self.local_files_only = local_files_only
        self._model: Any = None
        self._tokenizer: Any = None
        self._torch: Any = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError:
            raise TranslationError("Install the local dependency extra and CUDA PyTorch") from None
        if not torch.cuda.is_available():
            raise TranslationError("CUDA is unavailable; check the PyTorch build and NVIDIA driver")
        try:
            options = {"revision": self.revision, "local_files_only": self.local_files_only}
            tokenizer = AutoTokenizer.from_pretrained(self.model_name, **options)
            model = AutoModelForCausalLM.from_pretrained(
                self.model_name, dtype=torch.float16, **options
            ).to("cuda")
            model.eval()
        except (OSError, RuntimeError, ValueError):
            # Provider exceptions may include credentials or paths. Do not copy
            # their messages into user-visible errors or later log files.
            raise TranslationError("Could not load the local model on CUDA") from None
        self._torch, self._tokenizer, self._model = torch, tokenizer, model

    def translate(self, text: str, *, source_lang: str, target_lang: str) -> str:
        """Generate only translated text; reject oversized or unfinished output."""
        try:
            messages = translation_messages(text, source_lang, target_lang)
        except ValueError:
            raise TranslationError("Supported language codes are en and de") from None
        if not text.strip() or source_lang == target_lang:
            return text
        self._load()
        try:
            prompt = self._tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
            )
            inputs = self._tokenizer(prompt, return_tensors="pt", add_special_tokens=False)
            input_length = inputs["input_ids"].shape[-1]
            if input_length > self.max_input_tokens:
                raise TranslationError(
                    "Paragraph exceeds the input token limit; splitting is required"
                )
            if input_length + self.max_new_tokens > self._model.config.max_position_embeddings:
                raise TranslationError("Requested generation exceeds the model context window")
            inputs = inputs.to("cuda")
            with self._torch.inference_mode():
                output = self._model.generate(
                    **inputs,
                    do_sample=False,
                    max_new_tokens=self.max_new_tokens,
                    pad_token_id=self._tokenizer.eos_token_id,
                )
            generated = output[0, input_length:]
            eos = self._model.generation_config.eos_token_id
            eos_ids = eos if isinstance(eos, list) else [eos]
            if not len(generated) or generated[-1].item() not in eos_ids:
                raise TranslationError("Translation did not finish within the output token limit")
            result = self._tokenizer.decode(generated, skip_special_tokens=True).strip()
            if not result:
                raise TranslationError("The model returned an empty translation")
            return result
        except (OSError, RuntimeError, ValueError):
            raise TranslationError(
                "Local translation failed; check GPU memory and model configuration"
            ) from None
