# Within-sentence formatting evaluation

## Run 01 review (2026-10-07)

Reviewed the generated Markdown, JSONL issues and console log. All 20 translation
and alignment calls completed with zero alignment failures and no retained-original
units. Six formatting warnings comprise one split, two expansions and three drops.

| Case | Observed result |
| --- | --- |
| A | Bold `Klassifikationsmodell` and italic `neue Beobachtungen` cover the intended phrases. |
| B | Bold splits into `schaltete` and `aus`; the split is logged as intended. |
| C | Link expands to `schaltete das Licht aus`, with the exact URL/title and an expansion warning. |
| D | Bold is dropped. Translation elides the first occurrence of `model` in `second model` and the later repeated checking verb. The unresolved range is the first `model`, not evidence that a later occurrence should receive its formatting. |
| E | The first link is dropped: `user` is unresolved although `Bedienungsanleitung` translates the complete phrase. The independent `Einstellungsfeld` link survives with its URL/title. Raw links are needed before selecting a correction for the first compound. |
| F | Outer bold survives; inner italic is dropped because the correspondence joins `classification` and `model` into `Klassifikationsmodell` across the inner source boundary. No unique target subword boundary is established. |
| G | The intended phrase is bold and the inline code is unchanged; no visible marker remains. |
| H | HTML link expands as in C, retaining the exact attributes and `&amp;` spelling. Expansion is logged. |
| I | Bold begins at `funktioniert` and ends after `Das zweite Modell`, preserving the intended partial boundaries across sentences. |

The three split/expansion warnings describe accepted behavior, not failed
restoration. D-F expose distinct limits: source ellipsis, an unresolved part of
a compound translation, and a many-to-one correspondence crossing a formatting
boundary. They should not be addressed by one blanket relaxation. A focused next
investigation is E (`user guide` / `Bedienungsanleitung`) using fixed source/target
text and inspecting raw word links. Keep D and F as conservative controls.

Translation time was 22.429 seconds, alignment 0.458 seconds and planning 0.005
seconds; no marker-only unit bypass occurred. The console reported 32.2 seconds
at the last segment. The measured components exclude some setup and processing;
these figures do not constitute a controlled performance comparison.

## Purpose

The long fixture demonstrated formatting around complete translation units.
`docs/examples/markdown-inline-scopes.en.md` instead exercises partial units and
word correspondences. No production policy changes accompany this fixture.
The first model results are reviewed above; passing deterministic tests does not establish
linguistic alignment quality.

## Compound alignment comparison

### Experimental local review

#### Controlled conflict checks (2026-10-09)

Deterministic tests now exercise two neighboring unresolved scopes and confirm
that their proposals use the original baseline independently. A final report
check rejects every candidate whose source or target window overlaps another
candidate window, regardless of review order. Rejected rows retain their evidence
and list `conflicts_with`; disjoint candidates remain proposals, never applied
repairs. Adjacent half-open windows do not overlap. Overlapping optical scopes
are conservatively deferred too, until joint validation exists.

An explicit negative-evidence test also supplies consistently swapped anchors for
two identical occurrences. Structural checks still produce a candidate for the
wrong occurrence: there is no independent linguistic evidence to contradict the
anchors. This documents a limitation, not an approved automatic correction.
The experiment must remain subject to manual review; passing these tests does
not establish safety for automatic production integration.

#### Boundary comparison suite

`tests/fixtures/alignment/local-review-boundaries-en-de.json` adds four manually
written fixed translation pairs with eight explicitly indexed link scopes:
repeated labels, reordered clauses, neighboring compounds and an omitted modifier
next to a repeated phrase. These are diagnostic inputs, not newly generated
model translations. None is required to produce a candidate; an already resolved
scope or unsafe window should be skipped.

```bash
python -m scripts.evaluate_alignment \
  --suite tests/fixtures/alignment/local-review-boundaries-en-de.json \
  --backend awesome --model aneuraz/awesome-align-with-co \
  --revision 777756717e1fa9556e304d4d5db173ee386b9c16 \
  --thresholds 0.001 --local-review \
  --output local-data/alignment/local-review-boundaries-run-01.json
```

Review raw links and proposed target offsets by occurrence, not word spelling
alone. Repeated labels must retain separate destinations. Reordered or grouped
anchors must not supply an arbitrary window. Neighboring proposals are evaluated
independently against the same baseline; even two successful proposals do not
establish that their combined application would be safe. The omitted adjective
must not be attached to a nearby occurrence or to `aktuelle`. If no case exercises
a particular retry path, record that limitation instead of claiming it passed.
Production behavior and acceptance rules remain unchanged.

##### Boundary run 01 findings (2026-10-08)

Reviewed `local-review-boundaries-run-01.json`: four baseline evaluations, eight
scopes, zero execution errors. Seven scopes were skipped and one proposal was
rejected; only one extra alignment call occurred and no candidate was produced.

- Repeated guide labels: the baseline already links each source occurrence to
  its corresponding target occurrence (starts 14 and 49). Both scopes skip retry.
- Reordered clauses: both words in `user guide` are unaligned, but its target
  anchors appear in reverse order. Review skips with `empty_or_reordered_window`.
  The settings compound is already resolved and requires no retry.
- Neighboring compounds: both scopes are resolved in the baseline and skipped.
  This case therefore does not exercise two neighboring repair attempts or prove
  safe combined application of proposals.
- Repeated guide with omission: `outdated` remains unaligned after the sole local
  call and the proposal is rejected. The current guide stays linked to the second
  occurrence (the compound starts at 58); no repair is attempted for that scope.

The observed selection and rejection behavior is conservative. Repeated-occurrence
identity is correct in these baseline links, but successful local repair amid
repeated or neighboring failures remains untested by these model results. Together
with the earlier E candidate, the evidence supports the evaluator experiment,
not enabling automatic production repairs. A further step should test independent
and combined proposal conflicts deterministically before any integration.

#### Local run 01 findings (2026-10-08)

Reviewed `compound-local-run-01.json`. All six baseline evaluations completed
without errors. Seven scopes produced one candidate, one rejection and five
skips, with only two additional alignment calls.

- E: the exact local source `user guide` is compared with
  `Bedienungsanleitung,`. Both source words link to `Bedienungsanleitung`.
  The proposed link covers target `[14,33)`, excluding the comma in the window
  `[14,34)`. The independent settings link remains unchanged at `[49,65)`.
  Manual inspection supports this candidate for this fixed pair.
- The omitted-adjective control remains rejected: `outdated` is still unaligned.
- F is skipped because its drop is a crossing-boundary case rather than an
  unresolved-source case. No new subword boundary is guessed.
- D is skipped because the source gap before the right anchor contains a comma,
  not whitespace alone. This is a window-selection rejection, not proof that
  a local aligner can recognize the ellipsis.
- The already resolved shorter cases and E's independent link require no retry.

This demonstrates a useful conservative proposal for E without falsely repairing
the included negative controls. It does not establish general fallback accuracy;
production translation remains unchanged. Before integration, broaden the fixed
evaluation to repeated target phrases, ambiguous/reordered anchors and multiple
nearby failed scopes, and keep proposal acceptance separate from linguistic
review.

The evaluator accepts `--local-review` and fixture `scopes` with IDs, half-open
source character ranges and optional link destinations. Each fixture pair is the
fixed evaluation boundary; this prototype does not infer sentence pairings.
Only `unresolved_source` drops qualify. Immediate surrounding anchors must each
have one source and target range, appear in target order and be separated from
the source scope by whitespace only. The target window is the unchanged text
between those anchors, trimmed only at its outer whitespace. Existing links may
not cross either window boundary. Marker-bearing cases are skipped.

Each eligible scope gets at most one extra alignment call at the configured
threshold. All proposals are independent against the original baseline. They
must resolve every non-whitespace source character, preserve existing local
correspondences and pass formatting projection without losing or changing any
previously valid scope. Reports retain the original alignment, local windows,
raw local results, candidate alignment/projection when available, call count and
explicit skip/rejection/error reasons. `candidate` means structural checks passed
and manual review is required, not linguistic correctness or an applied repair.
Expected local execution errors set the evaluator's exit code to 1; a conservative
skip or rejection is an evaluation result rather than an execution failure.

After running the milestone check:

```bash
python -m scripts.evaluate_alignment \
  --suite tests/fixtures/alignment/compound-en-de.json \
  --backend awesome --model aneuraz/awesome-align-with-co \
  --revision 777756717e1fa9556e304d4d5db173ee386b9c16 \
  --thresholds 0.001 --local-review \
  --output local-data/alignment/compound-local-run-01.json
```

Inspect E for a useful candidate and D/F plus the omitted-adjective case for
unsafe proposals. Refusing a window is an acceptable conservative outcome. No
production translation, projection or threshold is changed by this experiment.

### Run 01 findings (2026-10-07)

Reviewed `local-data/alignment/compound-run-01.json`: all 18 evaluations completed
without errors on the pinned checkpoint. All three thresholds produced identical
raw alignments for each of the six cases, including uncertainty ranges.

- E still leaves `user` unaligned and links only `guide` to `Bedienungsanleitung`.
- The shorter sentence links both `user` and `guide` to the compound at every
  threshold. The explicit translation links them to `Benutzer` and `Anleitung`.
- The omitted adjective `outdated` remains unaligned in all settings.
- F consistently joins `classification` and `model` to `Klassifikationsmodell`;
  this still crosses the inner emphasis boundary.
- D leaves the elided first `model` of `second model`, a comma and the later
  `checks` unaligned. No threshold supplies a missing occurrence.

Keep the production threshold at 0.001. This experiment provides no evidence for
changing it: the failure is sensitive to context, but these extraction thresholds
do not alter it. The manually shortened sentence is a diagnostic control, not a
safe production repair; selecting a target substring using incomplete links could
reinforce a wrong association. Any local re-alignment fallback needs separately
defined source/target window boundaries, rejection criteria and negative cases.
The current production behavior remains conservative dropping with diagnostics.

### Reproduction

`tests/fixtures/alignment/compound-en-de.json` freezes the observed source/target
pair from E and the boundary/ellipsis controls F and D. Three manually written
diagnostic variants isolate shorter context, an explicit non-compound translation,
and an omitted adjective. These variants are not model outputs. Expected entries
are human review hints, not exhaustive links or computed accuracy scores.

```bash
python -m scripts.evaluate_alignment \
  --suite tests/fixtures/alignment/compound-en-de.json \
  --backend awesome --model aneuraz/awesome-align-with-co \
  --revision 777756717e1fa9556e304d4d5db173ee386b9c16 \
  --thresholds 0.001 0.0005 0.0001 \
  --output local-data/alignment/compound-run-01.json
```

This evaluates six fixed pairs at three extraction thresholds without translating
them again. The production threshold remains 0.001. Inspect raw source/target
ranges and connected word groups, not only unresolved counts. Check whether both
`user` and `guide` join the correct compound and whether added links mistakenly
absorb `outdated`, attach repeated words to the wrong occurrence, or cross the
`classification` formatting boundary. Lower thresholds are diagnostic candidates,
not automatic improvements. The first results are reviewed above.

## Run

From the repository root in Git Bash, using the existing local checkpoint:

```bash
set -o pipefail
doc-lingo docs/examples/markdown-inline-scopes.en.md \
  --target-lang de --aligner awesome \
  --alignment-model "$USERPROFILE/.cache/huggingface/hub/models--aneuraz--awesome-align-with-co/snapshots/777756717e1fa9556e304d4d5db173ee386b9c16" \
  --output local-data/translations/markdown-inline-scopes-run-01.de.md \
  2>&1 | tee local-data/translations/markdown-inline-scopes-run-01.console.log
```

Use a new suffix for subsequent runs. Exit code 3 means warnings; inspect the
output and any `.issues.jsonl` report together. No issues file is expected when
there are no warnings. Record statistics from the console without treating a
single run as a performance benchmark.

## Review cases

| Case | Check |
| --- | --- |
| A | Bold and italic cover their respective translated noun phrases, excluding surrounding prose. |
| B | If the translated verb is discontinuous, optical emphasis may split; inspect both pieces and the split warning. |
| C | For the same sentence as B, the link should span the continuous envelope of the verb's counterparts; inspect any intervening words and expansion warning. Preserve URL and title exactly. |
| D | Emphasis belongs to the first mention of the second model, not a later identical phrase or either first model. |
| E | Both URLs and titles remain exact; translated labels must not overlap or capture intervening prose. |
| F | Italic remains inside bold; inspect both translated boundaries and any dropped or split scopes. |
| G | Code remains byte-for-byte identical; prose is translated and the emphasis boundaries remain meaningful after marker restoration. |
| H | Apply the same link policy as C while preserving the exact HTML attributes and entity spelling. |
| I | The scope starts and ends inside different source sentences; both boundary fragments need word evidence. Formatting must not expand to include both entire sentences. |

The translation may choose a contiguous synonym instead of a split verb. Judge
the actual wording rather than requiring a particular German translation or
warning count. A dropped scope with a diagnostic is the conservative fallback,
not successful formatting restoration. Missing or ambiguous source words must
not be assigned arbitrary target positions to eliminate warnings.

For every case, record the visible formatting, linguistic boundary assessment,
warning action/reason and protected-content status. Distinguish wrong placement
from missing formatting; zero warnings do not prove correct placement. Any
follow-up change should address an observed failure with a focused regression
test rather than relaxing all partial-scope checks.
