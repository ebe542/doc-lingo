"""Optional upstream awesome-align inference on fixed sentence pairs."""

import re
from typing import Any

from doc_lingo.translation.alignment import AlignmentError, AlignmentResult, TextRange
from doc_lingo.translation.word_alignment import alignment_from_pairs

_WORDS = re.compile(r"\w+|[^\w\s]", re.UNICODE)


class AwesomeAlignAdapter:
    """Use upstream softmax extraction, layer 8, without local fine-tuning."""

    def __init__(
        self, model: Any, tokenizer: Any, *, device: str = "cpu", threshold: float = 0.001
    ) -> None:
        if not 0 < threshold < 1:
            raise ValueError("Softmax threshold must be between zero and one")
        self.model = model
        self.tokenizer = tokenizer
        self.device = device
        self.threshold = threshold

    @classmethod
    def load(cls, path: str, *, device: str = "cpu") -> "AwesomeAlignAdapter":
        try:
            from awesome_align.modeling import BertForMaskedLM
            from awesome_align.tokenization_bert import BertTokenizer

            tokenizer = BertTokenizer.from_pretrained(path)
            model = BertForMaskedLM.from_pretrained(path)
            model.to(device)
            model.eval()
        except (ImportError, OSError, RuntimeError, ValueError):
            raise AlignmentError(
                "Could not load awesome-align; check dependencies and model"
            ) from None
        return cls(model, tokenizer, device=device)

    def fits_input(self, text: str) -> bool:
        """Measure the same word/subword representation used by alignment."""
        return self._fits(text, 1.0)

    def fits_source(self, text: str) -> bool:
        """Reserve 25 percent of encoder capacity for target expansion."""
        return self._fits(text, 0.75)

    def _fits(self, text: str, fraction: float) -> bool:
        words = [match.group() for match in _WORDS.finditer(text)]
        pieces = [self.tokenizer.tokenize(word) for word in words]
        if any(not piece for piece in pieces):
            raise AlignmentError("Alignment tokenizer dropped an input token")
        limit = min(self.tokenizer.max_len, self.model.config.max_position_embeddings)
        return sum(map(len, pieces)) + self.tokenizer.num_added_tokens(pair=False) <= int(
            limit * fraction
        )

    def _encode(self, words: list[str]):
        pieces = [self.tokenizer.tokenize(word) for word in words]
        if any(not piece for piece in pieces):
            raise AlignmentError("Alignment tokenizer dropped an input token")
        ids = self.tokenizer.convert_tokens_to_ids([piece for word in pieces for piece in word])
        limit = min(self.tokenizer.max_len, self.model.config.max_position_embeddings)
        # awesome-align bundles the older tokenizer API, independently of the
        # installed Transformers version. Count its own added special tokens.
        if len(ids) + self.tokenizer.num_added_tokens(pair=False) > limit:
            raise AlignmentError("Alignment input exceeds the encoder token limit")
        encoded = self.tokenizer.prepare_for_model(ids, return_tensors="pt")["input_ids"]
        mapping = [index for index, word in enumerate(pieces) for _ in word]
        return encoded, mapping

    def align(self, source: str, target: str) -> AlignmentResult:
        matches = [list(_WORDS.finditer(text)) for text in (source, target)]
        left, right = [[TextRange(m.start(), m.end()) for m in side] for side in matches]
        if not left or not right:
            return AlignmentResult(source, target, unaligned=tuple(left))
        try:
            import torch
            from awesome_align import modeling

            # Upstream exposes these as module globals. Save/restore them for
            # sequential callers; concurrent awesome-align calls are unsupported.
            names = ("PAD_ID", "CLS_ID", "SEP_ID")
            missing = object()
            old = [getattr(modeling, name, missing) for name in names]
            try:
                for name, value in zip(
                    names,
                    (
                        self.tokenizer.pad_token_id,
                        self.tokenizer.cls_token_id,
                        self.tokenizer.sep_token_id,
                    ),
                    strict=True,
                ):
                    setattr(modeling, name, value)
                src, src_map = self._encode([m.group() for m in matches[0]])
                tgt, tgt_map = self._encode([m.group() for m in matches[1]])
                with torch.no_grad():
                    pairs = self.model.get_aligned_word(
                        src,
                        tgt,
                        [src_map],
                        [tgt_map],
                        self.device,
                        0,
                        0,
                        align_layer=8,
                        extraction="softmax",
                        softmax_threshold=self.threshold,
                        test=True,
                    )[0]
            finally:
                for name, value in zip(names, old, strict=True):
                    if value is missing:
                        delattr(modeling, name)
                    else:
                        setattr(modeling, name, value)
        except (ImportError, OSError, RuntimeError):
            raise AlignmentError("awesome-align execution failed") from None
        return alignment_from_pairs(source, target, left, right, pairs)
