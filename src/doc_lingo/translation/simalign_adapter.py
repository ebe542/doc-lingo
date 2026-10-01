"""Optional SimAlign bridge with exact source offsets and length checks."""

import re
from typing import Any

from doc_lingo.translation.alignment import (
    AlignmentError,
    AlignmentResult,
    TextRange,
)
from doc_lingo.translation.word_alignment import alignment_from_pairs

_WORDS = re.compile(r"\w+|[^\w\s]", re.UNICODE)


class SimAlignAdapter:
    """Evaluate Argmax or IterMax without modifying the translation service.

    Connected word-pair components become many-to-many links. Missing edges
    mean unaligned, not proven omission; no calibrated uncertainty is supplied
    by SimAlign. Marker identities must be handled separately by orchestration.
    """

    def __init__(self, engine: Any, *, method: str = "inter") -> None:
        if method not in ("inter", "itermax"):
            raise ValueError("Unsupported SimAlign matching method")
        self.engine = engine
        self.method = method

    @classmethod
    def load(cls, model: str, *, device: str = "cpu", method: str = "inter") -> "SimAlignAdapter":
        """Load an explicit model name or pinned local snapshot on demand."""
        try:
            from simalign import SentenceAligner

            engine = SentenceAligner(
                model=model, token_type="bpe", matching_methods="ai", device=device, layer=8
            )
        except (ImportError, OSError, RuntimeError, ValueError):
            raise AlignmentError(
                "Could not load SimAlign; check alignment dependencies and model"
            ) from None
        return cls(engine, method=method)

    def _check_length(self, words: list[str]) -> None:
        tokenizer = self.engine.embed_loader.tokenizer
        limit = min(
            tokenizer.model_max_length,
            self.engine.embed_loader.emb_model.config.max_position_embeddings,
        )
        encoded = tokenizer(
            words, is_split_into_words=True, truncation=False, add_special_tokens=True
        )["input_ids"]
        if len(encoded) > limit:
            raise AlignmentError("Alignment input exceeds the encoder token limit")
        pieces = [tokenizer.tokenize(word) for word in words]
        if any(not piece for piece in pieces):
            raise AlignmentError("Alignment tokenizer dropped an input token")
        if sum(map(len, pieces)) + tokenizer.num_special_tokens_to_add(pair=False) != len(encoded):
            raise AlignmentError("Alignment tokenizer mappings are inconsistent")

    def align(self, source: str, target: str) -> AlignmentResult:
        left, right = [list(_WORDS.finditer(text)) for text in (source, target)]
        source_ranges = [TextRange(m.start(), m.end()) for m in left]
        target_ranges = [TextRange(m.start(), m.end()) for m in right]
        if not left or not right:
            return AlignmentResult(source, target, unaligned=tuple(source_ranges))
        try:
            words = [[m.group() for m in matches] for matches in (left, right)]
            for sentence in words:
                self._check_length(sentence)
            pairs = self.engine.get_word_aligns(*words)[self.method]
        except (OSError, RuntimeError):
            raise AlignmentError("SimAlign execution failed") from None
        return alignment_from_pairs(source, target, source_ranges, target_ranges, pairs)
