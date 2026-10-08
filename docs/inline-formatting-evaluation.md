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
