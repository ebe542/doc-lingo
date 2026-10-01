# Alignment methods and initial comparison

## Extended-run review (2026-10-01)

Both extended runs completed all 16 cases without reported errors using fixture
fingerprint `76770300aa8f635055e678143706d9070caf7c8197fa6b1d83cebff844f5551f`.
Backend, CPU, layer, threshold, segmentation and package versions match; model
revisions differ as intended. Original reports and pending verdicts are unchanged.

The CO checkpoint retains its earlier improvements and adds correct `Open` to
`öffnen`, leaves omitted `Carefully` unaligned, and fixes `the` to `die` in the
added-adjective example. Split verbs, negation and the `input file` compound have
useful correspondences. Unaligned auxiliary `Do` in the CO negation result is
not itself evidence of a translation error.

Three important limitations remain:

- In `polite-keep`, CO links `Please` to `Lassen`, leaves `keep` unaligned and
  misses `bitte`. The base model also fails this case with an incorrect group.
- In `reordered-repeated`, CO separates `first`/`ersten` and `second`/`zweite`,
  but both models link the first source `model` to the first target `Modell`.
  Those occurrences refer to different entities after the active/passive rewrite;
  inspecting word strings alone would hide the error. Articles are also unsafe.
- In `two-markers`, the base model groups both markers; CO incorrectly swaps
  their identities (X0 to X1 and X1 to X0). The source and target strings contain
  intact markers: this is an alignment error, not marker corruption by translation.

Retain CO as the preferred experimental candidate, without claiming production
readiness or an accuracy percentage. Next, validate registered marker identity
deterministically and override conflicting statistical marker edges. This fixes
marker identity only; repeated ordinary words and phrase-level errors still need
separate handling before automatic formatting projection. Empty `ambiguous`
lists do not mean these errors were detected or that the matches are certain.

## Next experiment: alignment-trained checkpoint

Selected on 2026-10-01: `aneuraz/awesome-align-with-co`, revision
`777756717e1fa9556e304d4d5db173ee386b9c16`.
The [model card](https://huggingface.co/aneuraz/awesome-align-with-co/blob/777756717e1fa9556e304d4d5db173ee386b9c16/README.md)
attributes the model to the original awesome-align project and paper, lists
German and English among its languages, and declares BSD-3-Clause. This is a
third-party upload, not the neulab account; provenance is based on that card,
not an independently verified weight comparison with the authors' download.
The repository provides `pytorch_model.bin`, vocabulary, tokenizer files and a
BERT configuration with 512 positions, matching our loader's expected format.
Loading and the initial seven-case comparison succeeded (see the CO review below).

Use the unchanged seven-case fixture first, retaining layer 8, threshold 0.001,
CPU and the same segmentation. This isolates the checkpoint change. The CO
(consistency optimization) variant may improve coverage at the expense of
precision; the [upstream README](https://github.com/neulab/awesome-align)
explicitly notes that tradeoff. Inspect the omission case as well as `Read` and
`Keep`; do not choose the model solely by how few words remain unaligned.

```bash
python -m scripts.evaluate_alignment --backend awesome --model aneuraz/awesome-align-with-co --revision 777756717e1fa9556e304d4d5db173ee386b9c16 --output local-data/alignment/awesome-co-run-01.json
```

The existing runner already accepts model and revision arguments. No code,
dependency, threshold or default-model change is needed for this experiment.
No local fine-tuning is performed. Keep both earlier reports for comparison;
extend the fixture only after reviewing this run so its fingerprint stays
comparable. New cases should then be evaluated on both checkpoints.

Decision date: 2026-10-01. This covers the approaches considered for doc-lingo,
not an exhaustive survey. Alignment is separate from translation; no approach
guarantees correct formatting placement.

| Approach | Strength | Limitation | Decision |
| --- | --- | --- | --- |
| Original offsets | Exact source identification | Target word order and lengths change | Keep for source mapping only |
| Exact strings, numbers, content markers | Deterministic identity when unique and unchanged | No semantic alignment; repeated words and marker placement remain uncertain | Separate anchors, not the general aligner |
| Dictionaries and isolated phrase translation | Simple candidate generation | Context-dependent translations differ; duplicates remain ambiguous | Not the initial alignment method |
| SimAlign with mBERT | Local, contextual word representations; no own parallel training corpus | Additional encoder, finite context, fallible matches | First evaluation candidate |
| awesome-align | mBERT extraction and alignment-oriented fine-tuning/checkpoints | Additional integration and checkpoint selection | Second candidate if needed |
| fast_align / statistical corpus alignment | Established word-pair extraction | Requires parallel corpus estimation and preprocessing | Defer for this project |
| Translation-model attention or joint alignment | Can use translation internals | Architecture/provider coupling; attention alone is not a correctness guarantee | Defer to preserve provider independence |
| LLM-generated span mapping | Flexible instructions and phrase descriptions | Generation cost, invented offsets and model-dependent reliability | Not the initial baseline |

Sources: [SimAlign](https://github.com/cisnlp/simalign),
[SimAlign paper](https://aclanthology.org/2020.findings-emnlp.147/),
[awesome-align](https://github.com/neulab/awesome-align),
[fast_align](https://github.com/clab/fast_align),
[joint translation/alignment example](https://github.com/facebookresearch/fairseq/tree/main/examples/joint_alignment_translation).
The final two rows describe architectural tradeoffs, not measured doc-lingo results.

## SimAlign experiment

Compare Argmax (`inter`) and IterMax (`itermax`) using mBERT layer 8 and subword
matching. CPU is the initial default to avoid competing with the translation
model for GPU memory. Actual memory use and speed on the maintainer's machine
are unmeasured. No training is required. We use a separately installable extra:

```bash
python -m pip install -e '.[alignment]'
python -m scripts.check_milestone
python -m scripts.evaluate_alignment --output local-data/alignment/run-01.json
```

Keep the existing CUDA-enabled Torch installation. The upstream package lists
older tested versions. The first local CPU run succeeded with Transformers 5.17.0
(see the review below); this does not establish compatibility for other versions
or devices. The adapter tests use doubles and do not prove that compatibility.
No dependency downgrade is prescribed. Model download occurs only for the
explicit evaluation command. The report records the resolved snapshot revision,
package versions, tokenizer policy, device, timings and fixture fingerprint.
For repeat runs use `--revision <recorded-revision>` and a new output filename.
Reports never overwrite an existing file. CPU runs do not measure peak GPU memory.

The fixture `tests/fixtures/alignment/en-de.json` contains original synthetic
sentence pairs: simple text, a split verb, repeated words, terminology, omission,
addition and a marker. Expected correspondences are manual review hints, not
automatic gold scores. All verdicts remain pending; inspect incorrect links,
unaligned source text and discontinuous phrases before choosing a method.

The adapter tokenizes Unicode word runs and individual punctuation, preserving
character offsets. Combining marks and language-specific segmentation are not
linguistically normalized by this baseline. Word-pair graph components form
many-to-many links. Disagreement between methods is not automatically classified
as ambiguity; empty `ambiguous` does not assert certainty. Known marker identities
are not yet injected as anchors, so the marker case also probes that limitation.

Both encoder inputs are checked against tokenizer and model limits, including
special tokens, before upstream truncation can happen. Dropped tokens or
inconsistent tokenization fail explicitly. Long translated text may exceed the
aligner limit even when the translation model accepted the source. No silent
clipping or automatic alignment chunking is performed.

The active translation service remains unchanged. This experiment does not
restore document formatting or evaluate translation quality.

## Review of run-01 (2026-10-01)

For the next candidate, see the awesome-align instructions below.

The local `local-data/alignment/run-01.json` completed all 14 evaluations without
reported errors: SimAlign 0.4, Python 3.13.14, Torch 2.13.0+cu132, Transformers
5.17.0, CPU, mBERT revision `3f076fdb1ab68d5b2880cb87a0886f315b8146f8`.
Suite fingerprint: `6a259d449488977c9e8bd262d7143d529310c82d5a908c6a2045bbca2260f68e`.
The generated report remains unchanged, including its pending verdicts.

| Case | Argmax | IterMax |
| --- | --- | --- |
| Simple | Correct links | Same |
| Repeated words | Both occurrences correctly distinguished | Same |
| Terminology | Expected word correspondences recovered | Same |
| Split verb | `off` unaligned; `aus` not linked | `turned off` linked only to `schaltete`; `aus` still missing |
| Omission | Correctly leaves `red` unaligned | Incorrectly groups `Keep` and `red` with `behalten` |
| Addition | Incorrect `Read` to `Bitte`; `guide` to `Anleitung` is correct | Same |
| Marker | Marker identity matched; `Keep` unaligned | Additionally matches `Keep` to `lassen` |

Source coverage alone is not an accuracy measure: IterMax removes some gaps by
adding incorrect or incomplete links. Agreement between methods is not proof of
correctness either, as the addition case demonstrates. The small suite supports
keeping Argmax as a conservative baseline, not deploying either method for
automatic formatting projection. Compare another candidate before that decision.

Observed calls took about 12–32 ms after the first call (220 ms), excluding model
loading/download. The runner requests both matching methods internally on each
call, so these timings do not measure their isolated costs or prove one faster.
Memory consumption was not measured. These are fixed translation pairs; a missing
alignment does not mean the translation omitted the corresponding word.

## awesome-align comparison

Use the same fixture, CPU and mBERT revision as run-01. This first comparison uses
the upstream package's softmax extraction (layer 8, threshold 0.001) on the base
model, not an alignment-fine-tuned checkpoint. It therefore does not measure the
best published awesome-align configuration. Upstream code and defaults:
[run_align.py](https://github.com/neulab/awesome-align/blob/master/awesome_align/run_align.py).

```bash
python -m pip install -e '.[awesome]'
python -m scripts.check_milestone
python -m scripts.evaluate_alignment --backend awesome --revision 3f076fdb1ab68d5b2880cb87a0886f315b8146f8 --output local-data/alignment/awesome-run-01.json
```

The optional extra installs awesome-align 0.1.7, which contains its own BERT and
tokenizer implementation. Its loader requires `pytorch_model.bin`; the evaluation
command downloads that additional weight file into the same pinned snapshot.
No Transformers downgrade is requested. Actual compatibility with the current
Python/Torch stack was confirmed for the first CPU run described below. Offline
adapter tests use doubles; an optional test also checks the installed tokenizer.

Both adapters share conversion of word-pair graphs into character ranges and
use the same word/punctuation policy. Both reject overlong input before inference.
awesome-align's special-token globals are restored after each call; concurrent
awesome-align calls are not supported by this initial wrapper. Reports include
backend, package versions and extraction settings. Compare linguistic errors,
not just coverage; no method is activated for document formatting yet.

## Review of awesome-run-01 (2026-10-01)

All seven softmax evaluations completed without reported errors using
awesome-align 0.1.7 and Torch 2.13.0+cu132 on CPU. Model revision, fixture
fingerprint, layer and word segmentation match the SimAlign baseline. This is
the base mBERT checkpoint, not an alignment-fine-tuned model.

The split verb is now fully covered: `turned` maps to `schaltete` and `off` to
`aus`. The omission case correctly leaves `red` unaligned. Simple text, repeated
words and terminology retain the useful baseline correspondences. Two limitations
remain: `Read` incorrectly maps to `Bitte` rather than `lesen`, and `Keep` in the
marker case is unaligned even though `lassen` is present in the target.

For this small suite, awesome-align is the more promising next candidate than
SimAlign Argmax: it repairs the split-verb correspondence without introducing the
IterMax omission error. This is not evidence of general superiority or readiness
for automatic formatting projection. In particular, a formatted `Read` would
still be transferred incorrectly without further safeguards.

Calls took approximately 12–20 ms after the first call (40 ms), excluding model
loading and download. Different execution paths and a single run prevent a
reliable speed ranking. The original JSON and its pending verdicts remain
unchanged. Next evaluation should expand polite imperatives, split verbs,
repeated words and marker contexts before selecting a production default.

## Review of awesome-co-run-01 (2026-10-01)

All seven evaluations completed without errors at the selected CO revision.
The fixture fingerprint, software versions, CPU, layer, threshold and segmentation
match the awesome-align base-model run. `Read` now maps to `lesen`, and `Keep`
maps to `lassen` in the marker case. The other five cases retain the earlier
correspondences, including `off` to `aus` and the correctly unaligned `red`.
The original report is retained unchanged with pending verdicts.

The checkpoint passes the specific manual expectations of this small suite.
That supports further evaluation, not a claim of general correctness or an
automatic production switch. Calls took roughly 14–24 ms, excluding loading;
memory and repeatability have not been benchmarked.

### Expanded comparison

`tests/fixtures/alignment/en-de-extended.json` keeps the seven original cases and
adds nine synthetic pairs covering polite imperatives, another split verb,
reordered repeated words, omission, addition, two reordered markers, negation
and a compound noun. These are a separate evaluation suite, not pytest cases.
Expected phrases remain manual review hints. The initial suite is unchanged.
Run both checkpoints with identical settings and compare the full links, not
just source coverage or the listed expected phrases:

```bash
python -m scripts.evaluate_alignment --backend awesome --suite tests/fixtures/alignment/en-de-extended.json --revision 3f076fdb1ab68d5b2880cb87a0886f315b8146f8 --output local-data/alignment/awesome-extended-run-01.json
python -m scripts.evaluate_alignment --backend awesome --suite tests/fixtures/alignment/en-de-extended.json --model aneuraz/awesome-align-with-co --revision 777756717e1fa9556e304d4d5db173ee386b9c16 --output local-data/alignment/awesome-co-extended-run-01.json
```
