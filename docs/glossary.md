# Optional terminology glossary

See [evaluation files](evaluation-files.md) for available inputs and the current
command set. Paths under `local-data/` below are generated outputs.

Glossaries are reusable UTF-8 JSON files maintained by the user. They do not train
or modify a model. The initial example is `docs/examples/glossary-en-de.json`; its
terminology is illustrative and its model behavior still requires manual review.
It now contains 36 manually selected ML/AI entries; see
[scope and sources](examples/glossary-sources.md). The general filename does not
make its terminology suitable for every subject area.

Schema version 1 requires `source_lang`, `target_lang`, and a nonempty `entries`
array. Each entry has `source`, `mode`, and (except for `keep`) `target`:

- `keep`: preserve the matched original spelling.
- `translate`: insert the supplied target text verbatim.
- `annotate`: insert target text followed by the matched original in parentheses.

Matches ignore case, respect Unicode word boundaries, and prefer longer terms.
There is no stemming, plural handling, automatic term detection, or first-mention
state. Every match uses the rule. Whitespace inside a term must match literally;
a term interrupted by a source line break is not matched. Target wording is not
inflected automatically. Do not expect a glossary to repair sentence grammar.

If an entire segment matches one entry, apart from outer whitespace, the wrapper
renders that rule directly without calling the model. Outer spaces, tabs and line
endings remain unchanged. Translate/annotate targets receive normal sentence-start
capitalization; keep mode preserves the original case. Punctuation or other text
outside the matched term still requires translation through the protected path.
This handles standalone headings such as Classification without placeholder risk.

```bash
mkdir -p local-data/translations
doc-lingo tests/fixtures/translation_quality/long-technical-document.en.txt --target-lang de --glossary docs/examples/glossary-en-de.json --output local-data/translations/long-technical-document.marian-glossary.run-01.de.txt
python scripts/evaluate_translation_quality.py --backend marian --glossary docs/examples/glossary-en-de.json --output local-data/quality/marian-with-glossary-run-01
```

The format-independent `GlossaryBackend(backend, Glossary.load(path))` wraps a
translator and can be passed directly to `translate_document`. The base backend
still owns token limits and generation. Random per-segment placeholders protect
terms. Every expected placeholder must return exactly once; unexpected markers
with the same prefix are rejected. Model behavior can vary with the placeholders.
Exact counts do not prove correct placement or grammatical agreement.

If protection fails or the underlying backend reports a recovery in protected
text, the entire original segment is retained and reported using the existing
`on_issue` mechanism (CLI exit code 3). Strict library calls raise an error.
Reports contain original source, not masked text. Fatal model errors still abort.
This conservative fallback may retain more text than a translation without a
glossary. Assess both terminology improvements and fallback rates before adopting
a glossary for routine use. Compare against the no-glossary reports; the runner
records the glossary fingerprint without embedding its contents in metadata.

## Compressed input

The same `--glossary` option accepts UTF-8 `.json` and `.json.gz` files. Gzip is
handled by Python's standard library; no additional dependency or temporary
extraction file is needed. The parsed schema and fingerprint are identical for
equivalent plain/compressed input. Invalid or truncated gzip files fail loading.
See the [Python gzip documentation](https://docs.python.org/3/library/gzip.html).

Keep the example in readable JSON for Git review. To create a compressed copy
locally without overwriting an existing file, run in Git Bash:

```bash
mkdir -p local-data/glossaries
python - <<'PY'
import gzip
from pathlib import Path

source = Path("docs/examples/glossary-en-de.json")
destination = Path("local-data/glossaries/glossary-en-de.json.gz")
with destination.open("xb") as output:
    output.write(gzip.compress(source.read_bytes(), mtime=0))
PY
```

Compression reduces storage and transfer size, not the memory occupied by parsed
entries or the compiled matcher. Both formats currently load the entire glossary.
There is no database or automatic download of terminology.

## Measuring larger glossaries

The matcher uses a prefix trie: shared character prefixes follow the same path,
and the longest match at each eligible source position wins. Searching does not
iterate over every glossary entry at every position. Worst-case work still depends
on text length and maximum term length; this is not an Aho-Corasick automaton or a
claim of unconditional linear time. Trie nodes consume memory and must be measured.
Marker validation/restoration retains the shared scans from the previous version.

Run the offline benchmark separately from model inference:

```bash
mkdir -p local-data/benchmarks
python scripts/benchmark_glossary.py --output local-data/benchmarks/glossary-trie-run-01.json
```

Defaults measure 50, 1,000, and 10,000 synthetic shared-prefix terms, with ten
repetitions for no hits, near misses, a late entry, and dense repeated hits. The
report includes JSON/gzip sizes, load times, matcher construction time, median
end-to-end wrapper time using an echo backend, and a separately measured Python
allocation peak for loading/construction. OS file caches may affect load times.
Allocation tracing does not measure total process RAM or GPU memory. Synthetic
timings do not predict every natural-language glossary. Output files are never
overwritten; temporary input files are removed on success and failure.

The benchmark checks exact restored output, but says nothing about model quality.
Many hits can disrupt grammar or increase fallback rates. Run a fresh comparison:

```bash
python scripts/evaluate_translation_quality.py --backend marian --glossary docs/examples/glossary-en-de.json --output local-data/quality/marian-with-glossary-run-01
mkdir -p local-data/translations
doc-lingo tests/fixtures/translation_quality/long-technical-document.en.txt --target-lang de --glossary docs/examples/glossary-en-de.json --output local-data/translations/long-technical-document.marian-glossary.run-01.de.txt
```

Compare semantic verdicts, whole-segment fallbacks, terminology and grammar with
the no-glossary reports. Do not overwrite older reports. The expanded glossary has
a different fingerprint; no improvement or benchmark result is claimed before
these commands are run and reviewed.

## First measured results (2026-09-18)

The user ran `glossary-benchmark-v1.json` on Windows with Python 3.13.14.
Matching figures below are medians over ten repetitions with an echo backend.

| Entries | JSON bytes | Gzip bytes | Build time | No hits, 1,400 chars | Dense hits, 1,100 chars | Python load/build peak |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 50 | 5,191 | 398 | 0.68 ms | 0.185 ms | 0.222 ms | 0.12 MiB |
| 1,000 | 102,091 | 5,727 | 11.55 ms | 29.90 ms | 7.90 ms | 2.11 MiB |
| 10,000 | 1,020,091 | 55,299 | 121.47 ms | 3,647.14 ms | 915.45 ms | 21.14 MiB |

Gzip reduced the 10,000-entry synthetic file by about 94.6%, but did not solve
matching cost. The regex matcher scales poorly on this workload. The small example
is suitable for further quality evaluation; large bulk imports should wait for a
different matching implementation and the same benchmark rerun. These figures are
not general capacity guarantees. One load sample per format does not establish
that gzip is faster to load, and highly repetitive synthetic entries compress
better than many real glossaries.

The expanded Marian quality report has six passes, four minor issues, no major
issues, and no recorded fallbacks in ten examples. It corrects document retrieval
and retains the requested original terminology. Three examples introduce lowercase
sentence starts through verbatim glossary replacement; percent spacing remains a
minor issue in the fourth. The document-context case is `minor_issue`, included
in these totals. Random placeholders and the small development suite limit what
one successful run demonstrates. Sentence capitalization and scalable matching
remain follow-up work before treating the glossary as release-ready.


## Matcher and capitalization follow-up

The first measurements above describe the previous regex implementation. The
current implementation records `matcher: prefix-trie-v1` in benchmark reports and
`protected-terms-v2` in quality metadata. Rerun using new output paths:

```bash
python scripts/check_milestone.py
mkdir -p local-data/benchmarks
python scripts/benchmark_glossary.py --output local-data/benchmarks/glossary-trie-run-01.json
python scripts/evaluate_translation_quality.py --backend marian --glossary docs/examples/glossary-en-de.json --output local-data/quality/marian-with-glossary-run-01
```

Replacement targets in translate/annotate mode now capitalize their first lowercase
character at the start of translated text or after sentence-ending punctuation,
allowing whitespace and quotes. Position is evaluated in model output, so reordered
terms are handled. Soft line breaks alone do not start a sentence. Keep mode and
original terms in annotations remain unchanged. This is a punctuation heuristic,
not a grammatical parser: abbreviations and exceptional product spelling in target
text may require review. No general inflection or lowercasing is introduced.

Matching keeps original character offsets and Unicode word boundaries. Unicode
case variants such as dotted/dotless I, Kelvin sign, and long s are normalized per
character. Sharp s stays one source character, so it is not matched as two s's.
Case-equivalent duplicate terms are rejected when constructing the matcher.
New timings and quality results remain pending until the user runs these commands.

## Trie and current-fixture results (2026-09-18)

The user supplied `local-data/benchmarks/glossary-trie-run-01.json`. For the same
10,000-entry synthetic workload, no-hit matching dropped from 3,647.139 ms to
0.132 ms and dense-hit matching from 915.452 ms to 0.282 ms. Construction took
10.918 ms; traced Python loading/construction peak was 9.97 MiB instead of
21.14 MiB. At 50 and 1,000 entries, no-hit medians were 0.143 and 0.139 ms.
This supports the trie for these measured workloads, not an unlimited capacity
claim. No-hit and dense-hit inputs are still only 1,400 and 1,100 characters.

`marian-with-glossary-run-01` has 8 passes, 2 minor issues, no major issues and no
fallbacks across ten short cases. Capitalization is corrected. Remaining minor
issues are input terminology (Eingaenge rather than Eingaben) and percent spacing.
Document context passes and is included in these totals.

The committed long synthetic fixture produced one reported fallback: segment 3,
the heading `Classification`, remained in English after placeholder protection
failed. Other sections, list items, numbers, prohibitions and the closing
requirement are present. Thus the long document is only partially translated,
despite the short suite having no fallbacks. Grammar/word choice still needs
review: validation-data agreement is wrong, training becomes Ausbildung in a
heading, and unseen records are described as invisible records. Long lines in
the original first paragraph remain long, consistent with the current wrapping
policy. A useful follow-up is direct rendering when a complete segment exactly
matches a glossary term; no model inference is necessary for such a heading.

The subsequent `long-technical-document.marian-glossary.run-02.de.txt` review
confirms the direct-rendering fix: the heading is now Klassifikation and no
`.issues.jsonl` file exists for this run. All sections and the closing requirement
remain present. This establishes the specific heading fix, not perfect translation
quality. Validation-data agreement, Ausbildung as training terminology, unsichtbare
Datensaetze for unseen records, and Die Testdatensatz still require correction.
Other phrasing varies between runs because placeholder identities are randomized.
