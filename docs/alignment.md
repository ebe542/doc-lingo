# Alignment contract

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
