"""Local English-to-German translation with the pinned Helsinki-NLP model."""

from typing import Any, Protocol, Self, cast

from doc_lingo.translation.chunks import translate_chunks
from doc_lingo.translation.issues import RecoverableTranslationError
from doc_lingo.translation.protocols import TranslationError

DEFAULT_MODEL = "Helsinki-NLP/opus-mt-en-de"
DEFAULT_REVISION = "6183067f769a302e3861815543b9f312c71b0ca4"


class _LoadableModel(Protocol):
    """Instance operations used at the Transformers factory boundary."""

    def to(self, device: str) -> Self: ...

    def eval(self) -> Self: ...


class MarianBackend:
    """Translate en to de without chat prompts; load weights lazily on CUDA."""

    def __init__(
        self,
        *,
        max_input_tokens: int = 512,
        max_new_tokens: int = 511,
        local_files_only: bool = False,
    ) -> None:
        # Decoder output starts with one special token; reserve its position.
        if not 1 <= max_input_tokens <= 512 or not 1 <= max_new_tokens <= 511:
            raise ValueError("Marian limits: 1..512 input tokens and 1..511 new tokens")
        self.model_name = DEFAULT_MODEL
        self.revision = DEFAULT_REVISION
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
            from transformers import AutoModelForSeq2SeqLM, MarianTokenizer
        except ImportError:
            raise TranslationError(
                "Install the local extra with Marian tokenizer dependencies"
            ) from None
        if not torch.cuda.is_available():
            raise TranslationError("CUDA is unavailable; check PyTorch and the NVIDIA driver")
        try:
            options = {"revision": self.revision, "local_files_only": self.local_files_only}
            tokenizer = MarianTokenizer.from_pretrained(self.model_name, **options)
            model = cast(
                _LoadableModel,
                AutoModelForSeq2SeqLM.from_pretrained(
                    self.model_name, dtype=torch.float32, **options
                ),
            ).to("cuda")
            model.eval()
        except (ImportError, OSError, RuntimeError, ValueError):
            raise TranslationError(
                "Could not load Marian; check dependencies and model access"
            ) from None
        self._torch, self._tokenizer, self._model = torch, tokenizer, model

    def translate(self, text: str, *, source_lang: str, target_lang: str) -> str:
        """Translate a segment, splitting oversized input at source boundaries."""
        if (source_lang, target_lang) != ("en", "de"):
            raise TranslationError("This Marian model supports only en to de")
        if not text.strip():
            return text
        self._load()
        try:

            def fits(part: str) -> bool:
                inputs = self._tokenizer(part, return_tensors="pt", truncation=False)
                return inputs["input_ids"].shape[-1] <= self.max_input_tokens

            return translate_chunks(
                text,
                fits,
                lambda part: self._translate_chunk(
                    part, source_lang=source_lang, target_lang=target_lang
                ),
            )
        except (OSError, RuntimeError, ValueError):
            raise TranslationError("Marian input preparation failed") from None

    def _translate_chunk(self, text: str, *, source_lang: str, target_lang: str) -> str:
        """Generate one measured chunk and reject incomplete output."""
        try:
            inputs = self._tokenizer(text, return_tensors="pt", truncation=False)
            if inputs["input_ids"].shape[-1] > self.max_input_tokens:
                raise TranslationError("Segment exceeds the Marian input token limit")
            with self._torch.inference_mode():
                output = self._model.generate(
                    **inputs.to("cuda"),
                    do_sample=False,
                    num_beams=4,
                    num_return_sequences=1,
                    max_new_tokens=self.max_new_tokens,
                    # Override the checkpoint's competing total-length limit.
                    max_length=None,
                    early_stopping=True,
                    length_penalty=1.0,
                    renormalize_logits=True,
                    # Forced EOS at the length cap would disguise truncation.
                    forced_eos_token_id=None,
                )
            generated = output[0]
            if len(generated) <= 1 or generated[-1].item() != self._tokenizer.eos_token_id:
                raise RecoverableTranslationError(
                    "Marian translation did not finish within the output limit"
                )
            # Encoder-decoder output contains no source prefix to slice off.
            result = self._tokenizer.decode(generated, skip_special_tokens=True).strip()
            if not result:
                raise RecoverableTranslationError("Marian returned an empty translation")
            return result
        except (RuntimeError, ValueError):
            raise RecoverableTranslationError(
                "Marian generation failed; check GPU memory and configuration"
            ) from None
