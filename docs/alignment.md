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
