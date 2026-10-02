# Alignment methods and initial comparison

## Broader-run review (2026-10-02)

`awesome-co-holdout-run-01.json` completed all 30 cases without reported errors,
including the longest paragraph. Its fixture fingerprint matches
`1ec630ea5feb9606f76920dce187ba76b170fdc121ed8f4269a8d4b3bce7f225`.
The CO revision, CPU, layer 8 and threshold 0.001 match the planned settings.
This review consumes the previously unseen suite; it is now evaluation evidence,
not an untouched holdout for future tuning. Original report data and pending
verdict fields remain unchanged.

Many paragraph-level correspondences are useful, including the selected scopes
in the pipeline, recovery, training, backup and pronoun cases. However, the
backup paragraph leaves `restore` unaligned. In the longest paragraph, only
`Formatting` links to `Formatierungsinformationen`; `information` is unaligned.
Successful processing therefore does not establish complete phrase coverage.

Reordered entities remain the clearest failure pattern:

- `reordered-files` mixes the first `file` with `destination` and links that
  group to `Zieldatei`; `source` is unaligned and the second `file` links to
  `Quelldatei`.
- `reordered-servers` groups `primary` and `secondary` against `primären`, while
  the two server occurrences follow target order instead of entity identity.
- `reordered-two-models` links `smaller` to `größere` and `larger` to `kleineren`;
  the model occurrences are also assigned to the wrong entities.
- Repeated nouns with preserved order, including occurrences across sentences,
  are correctly distinguished in the two corresponding cases.

Compound terms such as `input file name` and `context window` have useful
many-to-one links. `processes` correctly links to `verarbeitet`. When the target
contains both a German term and its English expansion (RAG/API), the source
expansion links to the copied English words, leaving the German term without
links. This is a valid lexical correspondence but insufficient to decide which
rendering should inherit formatting. Both deliberate omissions remain unaligned;
the added politeness/explanation cases avoid assigning unrelated source words to
the added material.

All registered markers have exact identity links after correction. Only
`marker-reordered` changes: a raw group containing all three markers on both
sides becomes three individual identity links. `before` and `deleting` remain
unaligned even though their translations are present. Anchoring repairs marker
identity, not the surrounding prose.

The four formatting-scope cases provide useful lexical anchors, including
`turned off` to discontinuous `schaltete` / `aus` and a scope across a sentence
boundary. Target insertions such as `Sie`, `ist` and `der` are not necessarily
linked. A later projection policy must decide how to include such words and
handle discontinuous scopes; these results do not demonstrate restored formatting.

No result reports ambiguous ranges despite the incorrect entity links. Keep
0.001 and exact marker anchoring, but do not treat this adapter as sufficient
for reliable automatic formatting projection. Review uncertainty and conservative
fallback behavior before integration. No accuracy percentage is inferred from
the partial scope annotations, and no model/settings change follows this review.

## Broader fixed-pair evaluation

`tests/fixtures/alignment/en-de-holdout.json` adds 30 manually authored English /
German pairs, separate from the earlier tuning cases. Keep the CO revision,
CPU, layer 8 and threshold 0.001 fixed for the first run. The first run is now
reviewed above; these examples must not be described as an unseen holdout for
subsequent experiments.

Cases cover multi-sentence paragraphs (including a longer explanatory passage),
reordered repeated nouns, technical terms and abbreviations, intentional
omissions/additions, four explicitly registered marker cases, and formatting
scopes across sentence boundaries or discontinuous target phrases. The pairs
are authored references, not independently certified translations. Incomplete
or expanded targets are labeled as deliberate alignment stress cases.

`expected_spans` records selected manual review expectations as half-open Python
character offsets plus exact text slices in source and target. Multiple target
ranges can represent a discontinuous phrase; an empty target list denotes an
intentional omission. These are partial review annotations, not exhaustive gold
word links. The runner copies them into each report case but does not score them
automatically or require one statistical link to match an entire phrase.
Fixture tests check range consistency and marker preservation, not linguistic
quality. Formatting scopes contain plain text only: actual formatting projection
and document-adapter behavior are outside this evaluation.

```bash
python -m scripts.check_milestone
python -m scripts.evaluate_alignment --backend awesome --suite tests/fixtures/alignment/en-de-holdout.json --model aneuraz/awesome-align-with-co --revision 777756717e1fa9556e304d4d5db173ee386b9c16 --device cpu --anchor-markers --thresholds 0.001 --output local-data/alignment/awesome-co-holdout-run-01.json
```

Review ordinary word/phrase links separately from deterministic marker repairs.
Check occurrence identity for repeated nouns, missing versus incorrect links,
and coverage of the selected formatting scopes. Retain raw results and report
encoder-budget failures as failures rather than truncating long passages. This
is an alignment evaluation on fixed translations, not a translation-quality or
book-throughput benchmark. Existing baseline fixtures and reports stay unchanged.

## Threshold-run review (2026-10-02)

`awesome-co-thresholds-run-01.json` completed all 48 evaluations (16 cases at
three thresholds) without reported errors. It used the CO revision below, CPU,
layer 8 and registered-suite fingerprint
`e7f9c814b9e72cb9a4aa9e3c734cbd9b0d4d8d3b9fe9ebedc8b16b1d3738a3a3`.

Both raw and corrected alignments are identical at 0.001 and 0.01 for every
case. At 0.0001, only `reordered-repeated` changes: separate ordinal matches
become a less specific group linking both `first` and `second` to both target
ordinals. The incorrect identities of the repeated `model` occurrences remain
at all three thresholds. `polite-keep` also remains incorrect: `Please` links
to `Lassen`, while `keep` is unaligned.

Exact anchoring changes only `two-markers`, at every threshold, correcting the
swapped statistical links to X0-to-X0 and X1-to-X1. The marker text remains in
both alignment inputs; raw results preserve the original errors. This is a
deterministic identity repair, not an improvement in learned word alignment or
proof of correct linguistic placement. No result reports ambiguous ranges;
the remaining ordinary-word errors demonstrate why that is not a confidence
guarantee.

Keep the default threshold at 0.001. This small suite provides no evidence for
changing it, and lowering it reduces specificity in one case. Original report
data and pending verdict fields remain unchanged; this section records the
manual review. Automatic formatting projection still needs separate validation.

## Threshold comparison with exact marker anchors

The next experiment retains markers in both model inputs. No text is removed or
replaced before alignment. `--anchor-markers` applies exact identity correction
after extraction, and reports both `raw_alignment` and corrected `alignment`.
If correction fails, raw evidence is retained with an error; no corrected result
is reported. The runner never discovers a trusted registry by guessing from
model output. The new `en-de-registered.json` suite explicitly registers the
markers in the two marker cases; its other fields match the 16-case extended
suite. Old fixture files and their fingerprints remain unchanged.

Compare thresholds 0.0001, 0.001 (baseline), and 0.01 with the same CO snapshot,
CPU and layer 8. One model is loaded; each setting gets a separate inference.
The threshold is recorded per result; all manual verdicts remain pending.
SimAlign does not accept `--thresholds`. Thresholds must be distinct, finite and
strictly between zero and one. Existing commands retain the 0.001 default.

```bash
python -m scripts.check_milestone
python -m scripts.evaluate_alignment --backend awesome --suite tests/fixtures/alignment/en-de-registered.json --model aneuraz/awesome-align-with-co --revision 777756717e1fa9556e304d4d5db173ee386b9c16 --anchor-markers --thresholds 0.0001 0.001 0.01 --output local-data/alignment/awesome-co-thresholds-run-01.json
```

Review incorrect links separately from missing links. Corrected marker identities
do not count as a statistical quality improvement. Removing a mixed statistical
phrase can mark surrounding source text ambiguous; inspect those regions too.
Pay particular attention to `polite-keep`, entity identity in `reordered-repeated`,
and the omitted adjective/adverb cases. A higher threshold may remove false links
but also useful ones. These cases guide tuning; any preferred setting must later
be checked on additional held-out examples before adopting it. No layer tuning or
change to the active translation pipeline is part of this experiment.

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
