# Partial formatting across chunk boundaries

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
