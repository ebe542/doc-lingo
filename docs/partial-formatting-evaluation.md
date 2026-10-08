# Partial formatting across chunk boundaries

For the next comparison, see [within-sentence formatting evaluation](inline-formatting-evaluation.md).
It exercises boundaries that still require word correspondences after the
complete-unit improvement.

## Fifth model-run review (2026-10-06)

Reviewed `markdown-partial-long-run-05.de.md` and its console log after the
reported successful milestone check. The run finishes without warnings; no
issues JSONL file remains. Inspection of the actual Markdown confirms:

- A: the long bold passage is restored; opening and closing sentences remain
  outside the emphasis.
- B: outer bold and inner italic passages are restored with the intended sentence
  boundaries and valid nesting.
- C: both independent links are restored with their exact original URLs and
  titles. The intervening prose and surrounding sentences remain outside links.
- D: the span title, inline code, code element and excluded English sentence
  remain unchanged while surrounding prose is translated. No markers are visible.

All five scopes dropped in run 04 are now present at the inspected boundaries.
This demonstrates complete-unit projection for this fixture, not general
word-alignment accuracy or reliability of arbitrary within-sentence formatting.
The linguistic issues `Rechtssache C` and function calling rendered as `anrufen`
remain outside the scope of this formatting change.

There are still 83 translation calls, 83 alignment calls, zero alignment failures
and one bypassed protected unit. Translation time is 32.739 seconds (run 04:
36.208), alignment 2.067 seconds (2.007), and planning 0.043 seconds (0.043).
Single-run timing differences do not establish a performance improvement.

## Complete-unit projection follow-up (2026-10-06)

The implementation now records exact translation-call boundaries separately from
word links and uses fully enclosed units for structural formatting projection.
Partially enclosed units retain strict word-coverage checks. Marker validation,
cross-boundary correspondence checks, link conflicts and writer validation remain
active. Historical run-04 conclusions below describe the prior policy.

After the milestone check, run the document comparison with fresh output and
console-log suffixes `run-05`. Inspect all A-C scopes and their precise boundaries,
nested emphasis, both link destinations/titles, and protected content in D.
Fewer warnings alone do not demonstrate correct restoration. The user-run
model results are reviewed above; no inference was run during implementation.

## Fourth model-run review (2026-10-05)

Reviewed the run-04 Markdown, JSONL report and console log after the user reported
passing milestone checks. No alignment executions failed and no original text
units were retained. D preserves its HTML attributes, code and excluded English
sentence. A-C still lose all five tested formatting scopes under the unchanged
strict policy, although the reported unresolved ranges decrease substantially:

| Scope | Run 03 ranges | Run 04 ranges |
| --- | ---: | ---: |
| A bold | 82 | 23 |
| B bold | 82 | 23 |
| B italic | 20 | 7 |
| C first link | 51 | 11 |
| C second link | 23 | 7 |

Counts overlap across nested scopes and are not an alignment accuracy score.
Decoded remaining ranges mostly contain punctuation and function words such as
`the`, `of` and `to`, but also `need` and `intended`. Removing all unresolved
function words or punctuation would therefore neither establish correctness nor
solve every scope. The output still contains linguistic issues such as
`Rechtssache C` and function calling rendered as `anrufen`.

Translation orchestration calls and alignment calls both increased from 15 to
83. Measured translation time was 36.208 seconds (previously 36.369), alignment
2.007 seconds (previously 1.673), and planning 0.043 seconds (previously 0.089).
The protected-unit count remains one. These single-run figures show no large
observed runtime increase, but are not a controlled performance benchmark.

Sentence pairing improves reported correspondence coverage in this example;
it has not yet improved the rendered partial formatting. A separate next design
step could preserve known complete translation-unit boundaries as structural
evidence for scopes enclosing entire units, using word alignment only for
partially covered boundary units. Such a policy requires explicit unit metadata
and tests; it must not infer boundaries from target punctuation or manufacture
missing word links. No such policy change is included in this run.

## Missing-correspondence investigation (2026-10-05)

### Fixed-pair results

Reviewed `local-data/alignment/partial-formatting-run-01.json`: all four cases
completed without execution errors, using the pinned CO checkpoint and threshold
0.001. The expected correspondences were inspected in the actual links:

| Pair | Sentence alone | With neighboring sentences |
| --- | --- | --- |
| `checks` / `überprüft` | Linked | Source word unaligned |
| `translator` / `Übersetzer` | Linked | Linked |
| `verb` / `Verb` | Linked | Linked |

The isolated checks sentence leaves one comma unaligned; its contextual variant
instead joins two source commas to one target comma. The isolated translator
sentence leaves `the` and `of` unaligned; the contextual variant additionally
leaves `does` unaligned in the preceding sentence. These differences show why
coverage counts alone are not a correctness measure. In particular, grammatical
material may be absorbed into German contractions or inflection.

This small comparison supports investigating smaller, exact translation pairs;
it does not establish a universal sentence-level advantage. Unlike the original
long-chunk run, both translator variants recover the two inspected content words.
The next implementation should capture source/target pairs at translation time
and align those known units before merging offsets. Do not reconstruct pairs by
independently splitting finished target text. Retain the strict formatting policy:
the remaining unresolved punctuation and function words mean that smaller units
alone will not guarantee preservation of every partial scope.

### Setup and evidence

Decoded run-03 diagnostic offsets against the exact prepared source, using the
Markdown reader, `aligned_body` and `prepare_model_input`. Do not apply these
offsets directly to the original Markdown. A's bold scope has 82 unresolved
ranges; B has the same 82 for bold and 20 for italic; C's links have 51 and 23.
These are per-scope counts, not independent failures: nested scopes overlap.

The missing ranges include punctuation and function words, but also `checks`,
`prediction`, `translator` and `verb`. The attempted translation contains
`überprüft`, `Vorhersage`, `Übersetzer` and `Verb`. Thus punctuation handling alone
cannot solve this case. The JSONL ranges combine unaligned and ambiguous statuses
and do not preserve raw links, so they cannot establish the exact extraction
failure or prove that a lower threshold would help.

`tests/fixtures/alignment/partial-formatting-en-de.json` freezes two manually
reviewed sentence pairs from A, each alone and with its immediate neighbors.
The translations are copied from run 03 without corrections or new generation.
Expected pairs are review hints, not exhaustive annotations or automated scores.
The contextual variants are controlled windows, not the original runtime chunks.

Run the existing evaluator with the same checkpoint and threshold:

```bash
python -m scripts.evaluate_alignment \
  --suite tests/fixtures/alignment/partial-formatting-en-de.json \
  --backend awesome --model aneuraz/awesome-align-with-co \
  --revision 777756717e1fa9556e304d4d5db173ee386b9c16 \
  --thresholds 0.001 \
  --output local-data/alignment/partial-formatting-run-01.json
```

Review the actual links for the expected words, missing links and incorrect
additional links in both variants. Better sentence-level results would support
an experiment aligning exact source/translation units captured during generation.
They would not justify independently splitting target text and pairing sentences
by index. Translation can merge or split sentences. No production chunking,
threshold or formatting policy changes are made by this investigation.

## Sentence-pair implementation follow-up

The aligned path now makes a separate backend call for each heuristic source
sentence, subdividing further only when required by the alignment source budget.
Each returned translation is aligned with exactly that call's input, even if the
backend produces multiple target sentences. Backend-internal subdivisions are
not exposed by this interface. Links are merged into complete-segment coordinates
before formatting projection. Original separators, marker-only bypass, target
budget checks and conservative partial-scope validation remain in place.

Sentence detection uses the existing punctuation heuristic, not linguistic
parsing; abbreviations can produce imperfect boundaries. Unbudgeted aligners now
also receive sentence pairs. No additional translation pass is performed, although
the number of orchestration and alignment calls can increase.

After the milestone check, repeat the document command above with output suffix
`run-04` (including the console log name). Compare formatting warnings, protected
content, translation wording and timings with run 03. The fixed-pair experiment
does not guarantee that this document run will preserve all partial formatting.

## Third model-run review (2026-10-04)

Reviewed `markdown-partial-long-run-03.de.md` and its JSONL report. The report
contains five `formatting_dropped` records, all caused by `unresolved_source`:
one bold scope in A, both emphasis scopes in B, and both links in C. Their prose
is translated, but the output contains neither those emphasis wrappers nor the
two link destinations. Missing word correspondences still prevent partial-scope
projection even when every alignment call completes successfully.

There are no chunk-alignment failure or retained-original records. D now contains
translated prose with the HTML span and its exact title attribute, unchanged
`model.predict(data)` and `<code>dataset_id</code>`, and the exact excluded span
`<span translate="no">This sentence stays in English.</span>`. No protection
markers remain visible in the output. This establishes successful protected
content restoration for this case, rather than preservation by source retention.

The user supplied these console measurements for the run:

| Measurement | Value |
| --- | --- |
| Translation orchestration calls / seconds | 15 / 36.369 |
| Alignment calls / seconds | 15 / 1.673 |
| Alignment failures | 0 |
| Planning seconds | 0.089 |
| Bypassed protected units | 1 |

Translation accounts for approximately 95 percent of the measured time, including
lazy backend loading. These figures do not establish a runtime regression without
a comparable earlier measurement. The source-window reserve avoided encoder
overflow in this run; it cannot guarantee that every future target will fit.

The technical failures addressed by this follow-up no longer occur in this case,
but partial-formatting quality remains unresolved. Keep the conservative rule
unchanged and investigate missing word correspondences separately. Linguistic
issues also remain: `Case C` becomes `Rechtssache C`, and calling a function is
rendered as `anrufen` in D. Successful marker restoration is not evidence of
translation quality.

## First model-run review (2026-10-04)

Follow-up inspection of the retained attempted output established that marker
X2Z (the trailing excluded sentence) was lost; X0Z and X1Z remained intact.
The model produced unrelated German text in place of X2Z. Source retention was
therefore necessary. Chunk diagnostics now record the chunk number, global
source/target ranges, and exception cause, including explicit source/target
budget failures. Marker errors distinguish the affected side and missing,
duplicate or unexpected marker slots. A fresh run is needed to establish the
cause of the previously generic chunk failures before changing chunk sizing.

Reviewed `markdown-partial-long-run-01.de.md` and its JSONL report. The run
completed, but it does not establish successful real-model partial formatting:

- A: the long partial bold scope was dropped.
- B: both the outer bold and inner italic scopes were dropped.
- C: both independent links were dropped; their prose was translated.
- D: the entire original English segment was retained after content-marker
  validation failed. Protected code, attributes and excluded text survived via
  source retention, not successful translation and restoration.

The report contains nine records: three chunk-alignment failure warnings, five
`unresolved_source` formatting drops, and one retained-original warning for
missing, duplicate or unexpected markers. The generic chunk warnings do not
record their exception reasons; target-side encoder overflow is plausible but
not established by this report. Even outside the failed chunks, the recorded
source ranges show individual missing correspondences.

The conservative fallback avoided publishing corrupted protected content, but
the intended partial-formatting outcome was not achieved. Improve alignment
failure diagnostics before choosing a remedy. Investigate marker preservation
separately from word alignment. Do not weaken partial-scope coverage checks or
describe these outputs as successful formatting preservation. Translation quality
also needs separate review (for example, `Case C` became `Rechtssache C`).

Use `docs/examples/markdown-partial-long.en.md` after the whole-paragraph
formatting comparison. Its long passages reuse the same technical narrative
across scenarios, without repeating sentences within a passage. Formatting
does not cover the entire prepared segment, so whole-segment projection cannot
hide missing word correspondences.

## Run

For the diagnostic follow-up, use output suffix `run-03` and save console output:

```bash
set -o pipefail
doc-lingo docs/examples/markdown-partial-long.en.md \
  --target-lang de --aligner awesome \
  --alignment-model "$USERPROFILE/.cache/huggingface/hub/models--aneuraz--awesome-align-with-co/snapshots/777756717e1fa9556e304d4d5db173ee386b9c16" \
  --output local-data/translations/markdown-partial-long-run-03.de.md \
  2>&1 | tee local-data/translations/markdown-partial-long-run-03.console.log
```

The second run confirmed target-side encoder overflow in chunk 2 of A, B and C,
and loss of marker X2Z in D. The follow-up reserves 25 percent of awesome-align's
encoder window when planning source chunks, while still validating both actual
inputs against the full limit. This is a heuristic reserve, not an overflow
guarantee. No automatic retranslation is performed.

Sentence units containing only explicitly registered protection markers bypass
translation and alignment. Their original spacing and content are retained.
Ordinary prose containing markers is still translated, and unregistered
marker-like words never qualify for this bypass.

The console ends with `Alignment path statistics` as JSON: translation calls/time,
alignment calls/time/failures, planning time, and bypassed protected-unit count.
Times are wall-clock seconds for the aligned path only. Translation includes lazy
backend loading and its internal sentence generation; the call count is the
number of orchestration calls, not the number of generated sentences. Alignment
time includes budget validation and error reporting, but excludes initial model
loading. Planning time includes source sizing and tokenization. Legacy fallback
segments, rendering and file I/O are outside these measurements. Compare runs
on identical input/hardware and account for cold versus warm caches.

Run the quality gate first. Run the model comparison from the repository root
in Git Bash, using the already downloaded CO checkpoint:

```bash
python -m scripts.check_milestone
doc-lingo docs/examples/markdown-partial-long.en.md \
  --target-lang de \
  --aligner awesome \
  --alignment-model "$USERPROFILE/.cache/huggingface/hub/models--aneuraz--awesome-align-with-co/snapshots/777756717e1fa9556e304d4d5db173ee386b9c16" \
  --output local-data/translations/markdown-partial-long-run-01.de.md
```

Use a fresh output name for every run. Exit code 3 denotes warnings: inspect
the JSONL report before deciding whether text or formatting was lost. Do not
interpret the absence of warnings as proof of linguistic alignment quality.

## Review

| Case | Intended scope | Review points |
| --- | --- | --- |
| A | A long bold passage with unformatted opening and closing sentences | Outer sentences must stay unformatted; inspect retained, split or dropped emphasis and its diagnostics. |
| B | A partial bold passage containing a shorter italic passage | Check both translated boundaries and valid nesting; one dropped scope must not silently corrupt the other. |
| C | Two independent links within one long paragraph | Preserve each exact URL/title; check label boundaries, expansion and overlap warnings independently. |
| D | HTML span, code and excluded text | Preserve attributes, both code expressions and the excluded English sentence. |

The long paragraphs are intended to exceed the current encoder budget; the
production tokenizer determines actual chunk boundaries. The output report does
not record every successful chunk, so a visual output review alone cannot prove
which particular scope crossed a boundary. Deterministic tests with a two-word
budget separately establish multiple calls and partial/nested scope handling.

Those tests use controlled correspondences and test mechanics, not model quality.
They also deliberately leave a word inside one partial scope unaligned: only
that scope must be dropped, an independent link must survive, and the diagnostic
must use full prepared-input coordinates instead of chunk-local offsets.

Record model-run findings separately from passing automated checks. In
particular, `unresolved_source` remains an expected conservative fallback for
partial scopes; do not relax the rule merely to make this fixture look formatted.
