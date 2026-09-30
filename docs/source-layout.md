# Source layout extraction

`doc_lingo.documents.SourceLayout` retains an unchanged source string and a
tuple of `SourceRange` values. Each range contains four Python string offsets:
`outer_start`, `inner_start`, `inner_end`, and `outer_end`. End offsets are
exclusive. Offsets are local to that source string, not global file positions,
byte offsets, or positions in a translation.

```python
from doc_lingo.documents import SourceLayout, SourceRange

layout = SourceLayout("The **model** works.", (SourceRange(4, 6, 11, 13),))
text = layout.extract_text()  # "The model works."
```

The opening syntax is the original slice between `outer_start` and `inner_start`;
the closing syntax is between `inner_end` and `outer_end`. Symbols and link
destinations therefore do not need separate copies. The inner slice may itself
contain nested formatting. Ranges must be in source order, with parents before
children; a child must fit entirely inside its parent's inner slice. Crossing,
duplicate, out-of-bounds and unordered ranges are rejected. Empty inner slices
are allowed. Text without ranges is returned unchanged, including whitespace.

Extraction removes only the recorded wrappers. It does not parse syntax, decode
HTML entities or Markdown escapes, distinguish protected code from prose, or
assign formatting to translated text. Adapters will supply these semantics in
later changes. Not every document construct is an enclosing inline range.

This initial library building block is not connected to the translation service.
Existing readers, writers and marker protection remain active. Markdown/HTML
segments now expose opt-in discovery through `segment.source_layout()`; target
alignment and formatting restoration require separate work. No persistent clean-text coordinates are
stored. Original positions distinguish identical words at different locations.

## Adapter discovery

Call `source_layout()` on a segment returned by a reader. Plain text segments
return an empty range list. Markdown segments discover matched emphasis,
strikethrough and explicit link labels using parser rules, including nested
formatting and document-resolved reference links. HTML elements use the existing
source-preserving parser's opening and closing positions. Attributes remain in
the original outer slices.

Code, images, autolinks, implicit reference labels, excluded HTML and standalone
HTML events such as comments remain opaque. Open HTML elements spanning segments
do not receive invented closing positions. Unsafe or crossing layouts are kept
as source. Entities and escapes remain encoded. Consequently, extracted text is
an intermediate representation, not yet a ready-to-translate input. No alignment,
target rendering or change to the active translation service is included.

## Structured translation input

`segment.translation_input()` combines the discovered layout with the adapter's
existing protected ranges. Its `parts` partition the complete original segment
into `text`, `protected`, and `syntax` source slices. Recognized wrappers take
precedence over old protection ranges; unrecognized protected syntax remains
opaque. Parts store only source offsets and a role, not copies of their contents.
The layout still owns the outer/inner formatting relationships.

`prepared.text` omits recognized wrappers but retains protected slices verbatim.
It is an inspection view, not a backend request: code delimiters, excluded HTML,
entities and other opaque content may remain. Passing that string alone to a
model would discard its protection metadata. The active translation service has
not been switched to this representation.

Preparation neither splits sentences nor translates anything. A formatting range
covering multiple sentences stays attached to the entire source segment. Future
chunking and alignment must carry that relationship across translation units;
this change does not yet implement that mapping or target reconstruction.

## Validation cases

Before committing, cover plain text, emphasis, link labels, nested emphasis,
adjacent ranges, repeated words, Unicode, empty inner content and unchanged
line endings. Check invalid boundary order, negative and out-of-bounds offsets,
duplicates, crossing ranges, children inside delimiters and reversed input order.
Run `python -m scripts.check_milestone` after adding these offline tests.
