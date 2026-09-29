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
Existing readers, writers and marker protection remain active. Automatic
Markdown/HTML range discovery is the next step; target alignment and formatting
restoration require separate work. No persistent clean-text coordinates are
stored. Original positions distinguish identical words at different locations.

## Validation cases

Before committing, cover plain text, emphasis, link labels, nested emphasis,
adjacent ranges, repeated words, Unicode, empty inner content and unchanged
line endings. Check invalid boundary order, negative and out-of-bounds offsets,
duplicates, crossing ranges, children inside delimiters and reversed input order.
Run `python -m scripts.check_milestone` after adding these offline tests.
