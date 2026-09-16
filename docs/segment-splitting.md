# Oversized translation segments

Marian and Qwen translate sentence-sized units even when an entire paragraph
fits the context, to reduce the risk of long-input omissions. Each sentence is
further split when its actual tokenized input exceeds the available budget. Marian counts source special tokens. Qwen counts its full chat
template and instructions, and reserves `max_new_tokens` in the context window.
There is no character-to-token estimate and no source truncation.

The shared backend helper first prefers whitespace after sentence-ending
punctuation (`.`, `!`, `?`, optionally followed by closing quotes or parentheses).
If no such boundary exists, it uses whitespace between words. Subdivision chooses
a boundary near the middle and repeats until each part fits. This keeps calls
bounded without assuming tokenizer counts grow monotonically with text length;
it does not attempt to fill every model request to maximum capacity.

Sentence detection is a heuristic: abbreviations can look like sentence endings.
Source substrings are retained exactly, without decoding token slices. Whitespace
at split boundaries is inserted between the translated parts. Each part is
translated independently, so cross-part context and terminology may be weaker.
An indivisible word, URL, or other unbroken string is never split inside.
The CLI retains it in the original language and records an issue. Strict library
calls without an issue callback raise `TranslationError` instead. Very small Qwen budgets
that cannot accommodate the prompt and a word also fail explicitly.

The assembled result is still one `TextSegment`. Its ID, type, and adapter-owned
list prefix are unchanged. Progress advances once per completed document segment,
not per internal model call. Reading remains incremental across segments; the
source and translated text of the current segment must still fit in host memory.

Missing EOS, exhausted output budget, and empty model responses are recoverable
failures: the CLI retains the complete affected unit and records an issue.
Input splitting cannot guarantee that translated output fits its separate limit.
There are no generation retries or resume support. Fatal model-loading, input-preparation, and file errors abort the document. The
writer removes temporary output without publishing an unfinished destination or
modifying the source.

## Verification

Offline tests exercise source reconstruction, sentence/word boundaries, both
tokenizers through substitutes, prompt/context overhead, and document cleanup on
a later chunk failure. Run from Git Bash:

```bash
python scripts/check_milestone.py
```

For a manual GPU check, translate a TXT paragraph or wrapped list item exceeding
512 Marian tokens to a new destination. Review meaning across chunk boundaries,
list structure, and the single segment progress update. A successful offline test
does not establish translation quality for split text.

## TXT structure and wrapping

The TXT adapters recognize a conservative heading convention: at most six words
and 60 characters, an uppercase initial character, no final sentence punctuation
(except a colon), followed by prose with at least ten words. The preceding prose
must end in sentence punctuation or there must be no active prose. Active list
items are never split by this rule. Recognized headings receive type `heading`
and a separate translation call, even without surrounding blank lines.

This is a heuristic, not a general heading parser. Short wrapped lines can be
ambiguous and some headings will not be recognized. Use blank lines to separate
ambiguous sections; Markdown will provide explicit structure later.

When a translated multiline block collapses to a single line, the writer wraps
it at a width derived from the source (between 40 and 100 characters), using the
source line-ending style and hanging indentation for lists. Existing translated
line breaks are retained. Exact physical line positions are not guaranteed.
Blank separators, heading boundaries, list prefixes, and final endings remain
adapter-owned. No automatic test can prove that the model retained all meaning;
review long-document translations against the source.

## Original-text fallback and diagnostics

The CLI continues after an oversized indivisible word, unfinished/empty model
output, or a runtime/value failure during generation. It retains the entire
failed unit exactly, not a guessed word within that unit. Other units continue.
Unknown words that the model silently copies or mistranslates cannot be detected
reliably and will not automatically appear in the report.

For an output such as `book.de.txt`, issues are written incrementally to
`book.de.txt.issues.jsonl` (one JSON object per line). Each contains the original
text, sanitized reason, segment ID/type/number, paragraph number for prose, and
`page: null` for TXT. Headings and list items use segment numbering instead of an
invented paragraph/page number. The report contains document text: keep it local.
Existing reports are never overwritten. Empty reports are removed. A nonempty
report is retained if a later fatal failure prevents document publication; report
existence alone does not indicate that an output document was produced.

Exit code 3 means the document was published with retained original units; the
console shows the count and report path. Exit codes 0, 1, and 2 keep their existing
meanings. A report write failure aborts processing instead of silently losing the
record of untranslated content. There are no automatic retries.

Library callers opt in using `translate_document(..., on_issue=callback)` and
receive public `TranslationIssue` records. Without the callback, calls remain
strict. Backends distinguish `RecoverableTranslationError` from fatal
`TranslationError`. Model loading and validation happen outside recovery. The
callback is scoped to one segment through a context variable, avoiding mutable
backend callback state and preserving the provider-independent protocol.
