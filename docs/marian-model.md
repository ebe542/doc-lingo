# Marian translation backend

The default CLI and quality-runner model is
[Helsinki-NLP/opus-mt-en-de](https://huggingface.co/Helsinki-NLP/opus-mt-en-de),
developed by the University of Helsinki Language Technology Research Group.
The model card specifies CC-BY-4.0. This model license is separate from doc-lingo's
MIT code license. Model attribution and provenance must accompany redistribution.
Weights are downloaded from the original repository, not bundled with this project.

The backend pins revision `6183067f769a302e3861815543b9f312c71b0ca4` and uses
`AutoModelForSeq2SeqLM` with `MarianTokenizer`. It accepts only English-to-German
translation and requires CUDA. Imports and construction do not download models.
The tokenizer uses SentencePiece and Sacremoses, included in the `local` extra.

## Installation and comparison

Keep the working CUDA 13.2 PyTorch installation. From Git Bash:

```bash
python -m pip install -e ".[dev,local]"
python scripts/check_milestone.py
python scripts/evaluate_translation_quality.py --backend marian --output local-data/quality/marian-without-glossary-run-01
```

The last command performs real GPU inference and may download model weights.
Compare its report against the existing Qwen report on the same fixture version.
The regular CLI and evaluation runner default to Marian. Use `--backend qwen`
to select Qwen explicitly. Marian accepts only English-to-German requests.
The public library exports `MarianBackend`, which can also be passed directly to
`translate_document`.

## Differences from Qwen

Marian translates the source directly, without a chat template or prompt v2.
The report explicitly records `backend: marian`, `prompt_mode: none`, and empty
prompt identities. This compares complete translation approaches, not a controlled
prompt-only change. No automatic glossary expansion or first-mention memory is added.

The starting configuration is FP32, deterministic four-beam search, early stopping,
length penalty 1.0, and normalized logits. Source input is limited to 512 tokens
including special tokens. Output allows at most 511 new tokens, reserving the
decoder's starting token. The model's encoder and decoder have separate position
limits; the source length is not subtracted from the decoder limit.

The adapter splits oversized input at sentence or word boundaries, counting
special tokens in every chunk; it never truncates the source. Forced EOS is disabled
so reaching the output cap cannot masquerade as a completed translation. Missing
EOS and empty translations raise `TranslationError`. See
[segment splitting](segment-splitting.md) for boundary rules and limitations. Generation settings are based on the pinned model configuration with
the documented overrides above, and are recorded in the report.

The local CUDA run completed all ten examples. Manual review found eight passes,
one minor issue, and one meaning error; see the
[comparison results](translation-quality.md#local-model-comparison-2026-09-15).
Peak GPU memory has not been measured. The small suite does not establish general
superiority over Qwen. Offline tests use substitutes instead of model
downloads. See the [Marian documentation](https://huggingface.co/docs/transformers/model_doc/marian)
and [model configuration](https://huggingface.co/Helsinki-NLP/opus-mt-en-de/blob/6183067f769a302e3861815543b9f312c71b0ca4/config.json).
