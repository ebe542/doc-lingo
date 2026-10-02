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

This is opt-in and does not change the active translation or evaluation runner.

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
markers with original contents remain separate future steps. The contract adds
no model dependency and performs no translation or alignment itself.
