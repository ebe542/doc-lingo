# Alignment contract

## Exact content-marker anchors

`translation.marker_alignment.anchor_content_markers(result, prepared)` replaces
statistical marker links with exact registered identities. The alignment source
must equal the complete `ModelInput.text`; applying it to individual chunks
requires a future chunk-specific registry. Both strings must contain each
registered marker exactly once, with no unexpected or damaged markers in the
reserved namespace. Invalid input raises `AlignmentError` before any result is
modified; the caller will handle document-level recovery during integration.

Any statistical link touching a source or target marker is removed as a whole.
Remaining source portions of such a phrase become `ambiguous`, rather than
assuming the leftover target words correspond to them. Exact marker ranges are
removed from previous unaligned/ambiguous regions. Unrelated links remain intact.
No marker content is replaced and no model is called. Identity anchors do not
prove correct linguistic placement or resolve repeated ordinary words.

This remains opt-in and does not change active translation. The evaluation runner
can apply correction with `--anchor-markers` using explicit fixture registries.
`anchor_registered_markers(result, tokens=..., prefix=...)` shares the same
validation/correction logic without requiring a fabricated source document.

`doc_lingo.translation.TextAligner` defines `align(source, target)` for the exact
strings of one model call, before marker restoration or text normalization.
It has no document-format dependencies. An optional SimAlign adapter is available
for evaluation; the active translation path is unchanged. See the
[method comparison and run instructions](alignment-methods.md).

`AlignmentResult` binds links to those two strings. `TextRange(start, end)` uses
nonempty, half-open Python character offsets, not bytes, tokenizer positions or
original-document coordinates. `AlignmentLink` relates one or more source ranges
to one or more target ranges. For example, English `turned off` may correspond
to German `schaltete` and `aus` at separate positions.

Ranges within a link must be ordered and disjoint. Links may change order between
source and target. Reused or overlapping ranges across links are rejected: express
shared words as one many-to-many link instead. A phrase link does not imply an
exact correspondence between individual words inside that phrase.

Every non-whitespace source character, including punctuation and marker text,
must have a status: linked, `unaligned` (no counterpart found), or `ambiguous`
(no unique assignment selected). Whitespace may be omitted. Unlinked target text
is allowed for insertions. Uncertain regions must not trigger automatic formatting
transfer. Structural validation cannot certify linguistic correctness, and no
algorithm-independent confidence score is assumed.

Operational failures use `AlignmentError`; messages must not contain document
contents or credentials. Linguistic uncertainty belongs in the result. Each
implementation must return the unchanged input strings in its result.

Later orchestration will validate content markers and determine their exact
identities separately. Marker identity does not prove correct linguistic placement.
Marker mapping, alignment execution, formatting projection and replacement of
markers with original contents remain separate orchestration steps. The contract adds
no model dependency and performs no translation or alignment itself.

## Formatting projection policy

### Markdown rendering

`documents.markdown.rendering.markdown_scopes(layout)` assigns layout-index
identities to nonempty source scopes. Its opaque link target is the exact closing
suffix (destination/reference and optional title), not a normalized URL.
Pass these scopes through `restore_aligned_formatting`, then call
`render_markdown(layout, restored, environment=...)`. Reference links require
the original parser environment. The renderer reuses original Markdown wrappers
for emphasis, strong emphasis, strikethrough and explicit links; HTML wrappers
are currently dropped with an `unsupported_markdown_wrapper` diagnostic.

Disjoint and nested target ranges are rendered with parents opened first and
children closed first. Crossing ranges and overlapping links are dropped for
all participating scopes. Split ranges produce repeated wrappers. Expanded
links use one wrapper pair and keep their original suffix. The existing parser
then checks whether each inserted wrapper occupies the intended range. If
delimiter interactions prevent that validation, all inserted formatting in this
render call is discarded; the restored translated text remains unchanged.

The returned `MarkdownRendering` contains Markdown text and accumulated
`FormattingIssue` records. A dropped scope supersedes its split/expansion notice.
This is an opt-in inline renderer, not automatic escaping of translated prose,
HTML rendering, or an active writer/CLI path. The eventual service must forward
new rendering issues to its diagnostic callback and preserve document context.

### Source and restored-target bridge

`restore_aligned_formatting` connects prepared `ModelInput`, a matching alignment,
and explicitly classified formatting scopes in original segment coordinates.
It removes syntax from source offsets, accounts for content-marker lengths,
anchors marker identities, applies the projection policy and restores protected
content in one pass. Result target ranges address the restored text, while scope
references retain their original source coordinates. The adapter supplies scope
identities and link destinations; this layer never guesses formatting types.

Scopes that cut protected content or contain only removed syntax are dropped
with diagnostics. Missing, duplicate or damaged markers and mismatched model
inputs raise `AlignmentError` before restoration; fully protected segments must
bypass alignment. The function accepts one complete prepared segment, not a
chunk with offsets relative to a different string.

An optional `on_issue` callback receives existing `TranslationIssue` objects with
segment, paragraph and page context and `formatting_dropped`, `formatting_split`
or `formatting_expanded` actions. Diagnostics contain the restored translation
and projection reason. Returned projection issues remain available without a
callback. Callback failures propagate; no global issue context is changed.
This bridge is callable by the library but is not yet selected by the active
service or CLI. Markdown rendering and writer integration remain the next step.

### Projection rules

`project_formatting(alignment, scopes)` is an opt-in, format-independent policy.
Each `FormattingScope` has an adapter-owned unique identity and a `TextRange`
in the exact alignment source, not original-document coordinates. An optional
`link_target` distinguishes a link from optical formatting and stays unchanged.
Callers must map layout coordinates into model-input coordinates before calling
this API; it does not infer wrapper types or restore marker contents.

- Drop a scope if any source range is unaligned or ambiguous, if a selected
  many-to-many link crosses its boundary, or if it has no target correspondence.
- Merge target anchors separated only by whitespace. Split optical formatting
  at other gaps, including inserted words, and report the split as a risk.
- Expand a discontinuous link from its first target anchor to its last,
  including intervening text, and report the expansion.
- Drop all links whose resulting target ranges overlap, including nested links.
  Conflict resolution is independent of caller order. Optical styles survive.
- Sentence boundaries do not split a scope automatically. The same coverage
  and gap rules apply to scopes spanning one or more sentences.

The immutable result contains projected ranges and structured issues with scope
identity, action (`dropped`, `split`, `expanded`) and reason. Issues omit document
text and URLs. Callers must persist these issues with their document/segment
context when integrating the policy. The pure function itself performs no file
I/O and never changes translated text. Discarded links have a drop issue rather
than a successful-expansion issue.

This step does not activate alignment in `translate_document`, render Markdown
or HTML, or change the CLI diagnostic file. Document writers still need an
integration that resolves wrapper nesting, maps target coordinates after marker
restoration, and forwards issues to the existing diagnostic sink. Structural
coverage cannot detect a linguistically incorrect but complete alignment.
## Active Markdown orchestration

### Long segments and paired chunks

`AlignmentResult.units` records ordered, non-overlapping `TranslationUnit`
source/target ranges from actual translation calls, excluding inter-unit
separators. Word links and uncertainty remain unchanged. Marker anchoring carries
these ranges forward; invalid markers still reject restoration first.

A formatting scope enclosing a complete unit can use its full target range,
including punctuation and inserted words, without complete word coverage.
Partially enclosed units still require reliable word links. A link crossing
either side of a unit boundary prevents using that unit as structural evidence.
Projection combines complete-unit ranges with valid boundary word ranges; existing
style splitting, contiguous link expansion and overlap checks still apply.
These boundaries establish call provenance, not linguistic correctness. Even an
alignment execution failure leaves the exact translation pair known; its warning
remains logged, while fully enclosed units can retain their formatting.

Awesome-align additionally implements `ReservedTextAligner.fits_source`: chunk
planning uses 75 percent of its encoder window, while `fits_input` retains the
full limit for validation and fixed-pair evaluation. Registered marker-only
sentence units bypass both models; ordinary source sentences are translated and
aligned separately, with budget subdivision as needed. The sentence heuristic
is shared with backend chunking; it is not linguistic sentence parsing.
The CLI prints `AlignmentStatistics`; library callers can pass an accumulator
through `translate_document(alignment_statistics=...)`. See the partial-formatting
evaluation guide for measurement boundaries and reproducible console capture.

For the next comparison, see [partial formatting evaluation](partial-formatting-evaluation.md).
It covers partial scopes, nested emphasis and independent links with unformatted
surrounding text, without relying on the whole-segment exception.

A formatting scope enclosing the complete non-whitespace source segment can
cover the entire non-whitespace translated segment without individual word
links. The complete-segment bridge explicitly enables this rule; isolated
projection calls remain strict unless `complete_segment=True` is supplied.
Marker and document-structure validation still apply, and overlapping links
still conflict. Partial scopes retain the conservative coverage policy.
Dropped partial-scope issues include affected half-open `alignment_source_ranges`
in prepared model-input coordinates, not original Markdown coordinates. These
positions are included in JSONL validation diagnostics without additional text.

Aligners may implement `BudgetedTextAligner.fits_input(text)`. Awesome-align
measures its actual word/subword representation, special tokens and encoder
limit without inference. Source sentences exceeding that budget are split before
translation at whitespace boundaries. Markers and indivisible
words are never cut. Each translated chunk is aligned against precisely the
source chunk that produced it; target sentences are not paired heuristically.

Local links and unresolved ranges are shifted into full source/target segment
coordinates. Source separators are preserved between chunks. Projection and
marker restoration then run once, permitting formatting scopes and links across
chunk boundaries. Memory use remains proportional to one segment. Aligners
without the optional budget capability receive one call per heuristic source
sentence. A returned target is never split independently, even if the backend
produces multiple sentences. Backend-internal subdivisions remain opaque.

A longer-than-expected target or another local alignment error leaves only that
chunk unresolved and emits a warning; other chunk links remain usable. A scope
touching unresolved text still drops as a whole under the existing policy.
Indivisible oversized words reach the translation backend's existing recovery
policy. Backend recovery and invalid markers retain the original segment as
before. This does not guarantee translation quality or solve every target-side
encoder overflow; no automatic retranslations or silent truncation are added.

Use `docs/examples/markdown-long.en.md` for a real-model run with the same CLI
alignment options and a fresh output path. Inspect both the long bold scope and
the long link, HTML emphasis, protected inline code, and any warning report.

Supported complete HTML inline wrappers (`strong`, `em`, `b`, `i`, `span`, `a`,
`s`, `u`, `mark`, `small`, `sub`, `sup`) now participate in alignment, both in
Markdown inline text and in HTML text regions. Opening/closing tags, attribute
spelling, quoting and entity escapes are copied verbatim. HTML anchors use the
same contiguous expansion and overlap rules as Markdown links; optical wrappers
may split. Raw HTML rendering does not interpret Markdown emphasis syntax.
Excluded code/preformatted content, hidden/translate=no elements and comments
remain protected. Block tags stay adapter-owned; unsupported complete wrappers
retain the legacy path. No standalone HTML file format is added. Earlier notes
below about all HTML wrappers using the legacy path are superseded by this scope.

Aligned structure validation ignores only parsed `softbreak` tokens. Translations
may reflow a paragraph or list item without retaining its physical soft wraps.
Hard breaks, paragraph/list boundaries, table-cell boundaries, HTML and protected
code remain validated. Newlines are not removed before parsing, since that would
hide newly introduced block structure. The legacy translation path stays strict.

`translate_document(..., aligner=...)` now selects the prepared-input, alignment,
projection and rendering path for Markdown segments. The service supplies actual
segment/paragraph context to all issue callbacks. HTML-wrapper segments use the
legacy path until HTML rendering is implemented. Fully protected input bypasses
both models. Other document formats retain their existing path.

The writer receives `AlignedMarkdownSegment` evidence and re-renders its target
ranges. It also checks restored text against the source with known wrappers
removed; block, table-cell, HTML and protected-code constraints remain enforced.
No boolean flag bypasses structural validation. Backend recovery and invalid
markers retain the original segment. Alignment failures instead project an
unresolved alignment, retaining valid translation and reporting formatting loss.
The aligner consumes a complete prepared segment; encoder overflow is not
silently truncated. This does not yet implement per-chunk alignment.

CLI selection requires both `--aligner awesome` and `--alignment-model PATH`.
Loading happens once, on CPU, and expected loading errors produce normal CLI
errors. The model directory is caller-owned; no automatic alignment download is
performed. Formatting issues use the existing JSONL file and warning exit code 3,
with counts separated from retained-original failures. Older descriptions below
of components as opt-in standalone steps describe their individual APIs; the
explicit CLI option now connects those steps.
