# Embedded HTML text

Markdown translation includes visible text in raw HTML blocks and inline HTML.
This does not add a standalone `.html` input format or a browser rendering step.

```html
<div title="User guide">Hello <strong>world</strong>.</div>
```

The text can become `Hallo <strong>Welt</strong>.` inside the same `div`.
The tag spelling, whitespace, attribute order, quote style and `title` value
remain unchanged. All attributes are protected, including `alt`, `aria-label`,
`href`, `src`, `class`, `style` and `data-*` values. Attribute translation is not
part of this feature.

## Segments and exclusions

Block tags separate translation units, including headings, paragraphs, list
items and HTML table cells. Inline tags such as `strong`, `em`, `span` and `a`
stay within the surrounding text unit, preserving sentence context. Raw HTML
block text uses the progress type `html_text`. Inline HTML in Markdown retains
the enclosing Markdown segment type, including `table_cell`.

The following remain unchanged:

- `script`, `style`, `pre` and `code` contents;
- `head`, `template` and elements with a `hidden` attribute;
- an element with `translate="no"` and all descendants, even if a descendant
  specifies `translate="yes"`;
- comments, declarations, processing instructions and character references.

Exclusion context persists across blank lines and Markdown token boundaries.
Markdown code and link destinations are masked before analyzing inline HTML so
literal tags there cannot change that context. This tokenizer does not evaluate
CSS or JavaScript; visibility controlled by styles or scripts is not inferred.

## Source preservation and validation

Python's standard-library `HTMLParser` locates text using source offsets.
The writer replaces only the selected source ranges; it does not serialize a
DOM. No additional dependency is required. Syntax and excluded content use the
same protected ranges as Markdown. Line endings and surrounding whitespace are
kept from the source.

Validation compares exact non-text HTML events and the resulting element stack.
An element that originally contains visible text must still contain text after
translation, including text in nested elements. There is one narrow recovery:
newly emptied, attribute-free `strong`, `em`, `b` and `i` pairs can be removed
while retaining the translation. Their interior must contain only whitespace
or other newly emptied emphasis pairs being removed in the same repair.
Comments, images and other content are never deleted. Originally empty elements
remain allowed and are not removed. Links, spans and elements with attributes
continue to use source retention when emptied.

Repairs are enabled only when an issue callback is supplied. The JSONL report
records `action: "formatting_repaired"` and the reason
`Translation retained; newly empty emphasis removed`. Source retention uses
`action: "retained_original"`. CLI summaries count the two actions separately;
both require review and produce exit status 3. Strict library calls without a
callback still raise instead of silently losing formatting.

The writer recomputes each repair from the pre-repair translation before
publication. Other markup and structure must still pass the adapter's checks.
This check does not prove that the correct translated words remain inside each
nonempty element, nor does it improve the linguistic quality of the translation.
If a model adds, drops or alters tags, attributes or protected content, the
original segment is retained and reported through the existing issue mechanism.
CLI runs return status 3 for recovery; strict library calls raise
`RecoverableTranslationError`. Human review is still required for meaning and
the placement of inline emphasis.

This is conservative source processing, not browser error recovery. Fragments
with mismatched closing tags or unsupported declarations are kept unchanged.
HTML that relies on implicit closing tags is not repaired. HTML blocks whose
source differs from the parser content because of Markdown container prefixes
(for example a quoted HTML block) remain unchanged; ordinary inline HTML inside
a Markdown quote or list is supported. Unclosed source elements keep their
context through the remaining document. No HTML sanitization is performed.

## Manual validation

See the diagnostic report when a paragraph or link unexpectedly stays untranslated.

After running `python -m scripts.check_milestone`, translate the shared example
to a fresh output path from Git Bash:

```bash
doc-lingo docs/examples/markdown.en.md --target-lang de --output local-data/markdown-html.de.md
```

Review both the Markdown source and preview. Check translated HTML prose,
unchanged attributes and comments, retained code and the untranslated paragraph
with `translate="no"`. If present, inspect the output's `.issues.jsonl` report.

## Diagnostic reports

Rejected document translations and formatting repairs include an optional
`diagnostics` object in each JSONL issue:

- `attempted_translation`: the intermediate backend result, before source
  retention or formatting repair; `null` if a recoverable exception returned no
  text. This is diagnostic data, never an approved output.
- `stage`: `protected` means document placeholders have not been restored;
  `restored` means document syntax has been restored and failed adapter validation.
- `validation_errors`: concrete checks that failed, such as `missing_marker`,
  `duplicate_marker`, `marker_order_changed`, `damaged_marker`,
  `html_text_emptied: strong[0]`, or a Markdown token index and changed fields.
- `protected_fragments`: at the protected stage, a mapping from expected markers
  to original syntax. Other stages use `null`. Do not blindly substitute damaged
  or missing markers to manufacture a translated document.

For example, a `restored` candidate can show that a link label was moved outside
its brackets even though the URL stayed intact. A `protected` candidate shows
which markers the backend actually returned. A nested backend recovery may have
already retained part of its input; this field is the backend return value, not
a separate trace of every model generation. Older or unrelated reports may have
no diagnostics. Reports already on disk are not rewritten.

These additions explain existing checks; they do not relax link protection,
change sentence splitting, or improve model translation quality. For each new
manual run use a new output path and compare its report with its source.
