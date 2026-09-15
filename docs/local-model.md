# Local CUDA translation

## Installation in Git Bash

Use the project's Python 3.13 environment. Install the CUDA build explicitly
before the optional dependencies: a Python extra cannot select a pip index.

```bash
source .venv/Scripts/activate
python -m pip install "torch==2.13.0+cu132" --index-url https://download.pytorch.org/whl/cu132 && python -m pip install -e ".[dev,local]"
python -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CUDA unavailable')"
```

Pin the `+cu132` build explicitly: an installed `2.13.0+cpu` can satisfy a
`torch==2.13.0` requirement even when a CUDA index is selected. The explicit build
replaces that CPU installation without requiring a separate uninstall.

The expected runtime is CUDA 13.2 with CUDA available. The NVIDIA driver display
in `nvidia-smi` describes driver capability; `torch.version.cuda` identifies the
installed PyTorch build. The installation recipe follows the official
[PyTorch CUDA 13.2 instructions](https://pytorch.org/get-started/previous-versions/).
No TorchVision, TorchAudio, or locally compiled CUDA extensions are required.

## Backend and model

`HuggingFaceBackend` defaults to
[`Qwen/Qwen3-1.7B`](https://huggingface.co/Qwen/Qwen3-1.7B), revision
`70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`, from the supplied reference adapter.
The starting configuration uses FP16 on CUDA, no CPU fallback, and no quantization.
The RTX 3060 Ti has 8 GB VRAM; actual memory use and translation quality still
require local validation. Close competing GPU workloads if memory is insufficient.

Imports and backend construction load no model. The first translation downloads
the pinned model if absent and loads it once. Documents are processed locally;
model downloads still require network access. Use `local_files_only=True` after
the model is cached for offline loading. This public model normally needs no token.
The adapter honors standard Hugging Face authentication, but does not load `.env`.
The CLI loads `.env` from the current working directory with `override=False`.
Use `HF_TOKEN` for authentication; existing environment values take precedence.
The existing `.env` remains untouched. Direct library calls must load it explicitly
before importing the backend, as below. Do not source dotenv files as shell code.

Supported language codes initially are `en` and `de`. Empty input and same-language
requests return unchanged without loading a model. Thinking is disabled using
Qwen's chat template. Greedy decoding (`do_sample=False`) is the initial project
choice for repeatable runs; it is not a guarantee of identical results across
hardware or of translation quality. Qwen's model card recommends sampling for
general non-thinking tasks; compare quality before a production release.

The input limit is 2048 tokens including instructions; the output limit is 1024
new tokens. Oversized input is rejected rather than truncated. Missing EOS or an
empty response is rejected rather than published as a completed translation.
Automatic splitting and retries remain separate work. The model generates text,
so semantic accuracy and resistance to instructions inside source documents must
be evaluated with representative examples.

## Manual smoke check

This command downloads model files on first use and runs one real GPU translation:

```bash
python -c "from dotenv import load_dotenv; load_dotenv('.env', override=False); from doc_lingo import HuggingFaceBackend; backend = HuggingFaceBackend(); print(backend.translate('The document contains two paragraphs.', source_lang='en', target_lang='de'))"
```

The backend can also be passed directly to `translate_document`. The CLI still
does not invoke translation. Automated tests use substitutes for Torch and
Transformers, so they require neither CUDA nor model downloads:

```bash
python scripts/check_milestone.py
```

## Prompt identity

`translation/prompts.py` keeps system instructions and the direction template separately
versioned with a name, positive integer version, and SHA-256 fingerprint of their
exact UTF-8 text. Increment the affected version for every instruction change.
Fingerprinting catches edits even if the version bump is forgotten. Document
text is supplied as a separate user message and is not part of the fingerprint.
For reproducibility, record both prompt identities, model revision, token limits,
and installed package versions. No translation cache is implemented yet.
