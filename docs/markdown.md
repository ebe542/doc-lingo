# Markdown translation

The library exports `MarkdownReader` and `MarkdownWriter`. The CLI selects them
for `.md` files (case-insensitive), using the same translation service, backends,
glossary, progress callbacks and issue reports as TXT. Output must have the same
extension as the source; format conversion is not supported.

```bash
python -m pip install -e ".[dev,release]"
doc-lingo docs/examples/markdown.en.md --target-lang de --output local-data/markdown.de.md
```

The output directory must exist. Choose a new output name for each run. Local
translation still requires the `local` extra and the CUDA installation described
in [local-model.md](local-model.md).

## Supported content

- Paragraphs, ATX and Setext headings, block quotes, bullet and numbered lists.
- Wrapped lines within a paragraph or list item remain one translation unit.
  Separate paragraphs within a list item are separate units; nested items are
  separate units as well. Backend token limits can still require chunking.
- Emphasis, strong emphasis and strikethrough retain their source delimiters.
- Table headers and body cells are translated individually as `table_cell`
  segments. Delimiters, alignment rows, padding and empty cells are retained.
  Escaped pipes, inline code and link destinations remain protected. Inline HTML
  text in cells is translated too. Missing cells and surplus source cells are not
  rewritten. A generated line break or additional column triggers source retention.
- Inline link labels and explicit reference-link labels are translated. Link
  destinations, titles and reference definitions remain unchanged.
- HTML blocks and inline HTML translate visible text while preserving every tag
  and attribute. HTML paragraphs, headings, list items and table cells form
  separate text runs (`html_text` in HTML blocks). Nested inline tags keep the
  surrounding sentence together. See [HTML text rules](html-text.md).
- Inline code, fenced and indented code blocks, images (including alt text),
  and autolinks remain unchanged. Shortcut/collapsed reference links remain unchanged because
  their visible labels also identify their references.
- Leading YAML front matter is retained. An opening `---` without a closing
  `---` or `...` conservatively retains the entire document.
- UTF-8 BOM, blank separators, indentation and physical line endings are retained.
  Project-owned files use LF; user document line endings are preserved as supplied.

This is a conservative CommonMark adapter with table translation and
strikethrough. It is not full GitHub Flavored Markdown: task lists, footnotes,
math and other extensions are not supported. Do not rely on extension semantics
being preserved; review the rendered result before publication. Relative links
are not relocated when writing to another directory. Heading text changes may
also change renderer-generated anchors; fragment links are not rewritten.

## Preservation and recovery

`markdown-it-py` identifies document structure. The adapters retain original
source slices instead of rendering Markdown again. Syntax ranges use Python
string offsets in `TextSegment.protected_spans`; the translation service masks
internal ranges while translating the surrounding text together. Leading and
trailing protected syntax is kept outside inference. Models do not receive code
contents or link destinations.

Document and glossary markers now use `deterministic-prefix-v2`: candidate
prefixes derive from SHA-256 of the namespace and collision counter, using its
first 32 hexadecimal characters. The first unused candidate is selected, with separate `DLM`
and `DLG` namespaces and a case-insensitive collision check. Their existing
32-hex-character prefix shape and restoration checks are retained. The same
source and configuration therefore produce the same protected backend input
across repeated calls and process restarts. This removes marker randomness;
model/runtime reproducibility and translation quality still need validation.
The initial v1 trials were byte-identical but retained six original segments in
each run: the model shortened or lengthened the zero-padded marker prefixes.
V2 removes those long zero runs; its model behavior requires a new comparison.

Markers must return exactly once and in their original order. Markdown segments
also validate the parsed structure, link attributes and code after translation.
Lost markers, nested backend recovery or changed structure retain the original
segment with an issue in CLI mode (exit status 3); strict library calls raise
`RecoverableTranslationError`. The report's `original` field contains source text.
Optional `diagnostics` record the intermediate translation and the concrete
validation errors; the `protected` stage can contain unresolved markers and is
not a usable translated document. See [HTML text rules](html-text.md#diagnostic-reports).
These checks cannot prove semantic translation quality or correct placement of
emphasis within a translated sentence. Model-dependent marker preservation must
be checked using real translations.

Writers validate ordered IDs and structure before publishing a new output file
with the same atomic, no-overwrite hard-link approach as TXT. Direct writer callers
must supply complete translated segment text, including retained syntax.

The reader parses the entire document to resolve reference definitions and keeps
source and token data in memory. Translation remains lazy, but Markdown reading
is not bounded-memory streaming; the writer also parses its own source snapshot.
Unalignable normalized source blocks are preserved unchanged, not guessed.
Reader and writer must refer to the same unchanged source file.

## Validation

Run from the repository root in Git Bash:

```bash
python -m scripts.check_milestone
```

`tests/documents/markdown/test_markdown.py`, `tests/documents/markdown/test_markdown_tables.py`, `tests/documents/markdown/test_markdown_html.py` and
`tests/translation/test_protected_translation.py` cover offline
translation, context, identity reconstruction, protected content, malformed
markers, structure changes, cleanup, glossary composition and CLI selection.
The example above provides a separate manual CUDA smoke check. Compare source and
output in a Markdown preview; table text should be translated while table
structure, HTML tags and attributes, and code remain unchanged. Visible HTML text
should be translated; excluded HTML content must retain its original text.
