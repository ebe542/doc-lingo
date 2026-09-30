# Changelog

## [Unreleased]

### Fixed

- Allow translated prose to move around preserved Markdown inline elements.
  Keep checking nesting, nonempty inline containers, links and code contents.

### Added

- Opt-in Markdown and embedded HTML source-range discovery on document segments,
  with nested emphasis and explicit link labels. Opaque content is retained;
  the active translation path still uses existing protection.

- Opt-in source layout values with nested outer/inner ranges and wrapper
  extraction. Automatic adapter integration and translation alignment are not
  yet implemented; existing translation behavior is unchanged.

- Paired TXT, Markdown and embedded HTML quality fixtures with opt-in backend
  input capture, using the existing manual evaluation runner.

- Markdown reader/writer and CLI format selection, preserving source syntax,
  code and destinations. Table headers and body cells are
  translated separately while preserving delimiters and column alignment.
- Format-independent protected segment ranges and adapter validation, with
  original-segment retention and issue reporting when syntax protection fails.
- Offline Markdown regression tests and a portable manual translation example.
- Embedded HTML text translation with exact tag/attribute preservation, block
  text segments, inherited exclusions and HTML structure validation.
- Keep translations when newly emptied, attribute-free HTML emphasis can be
  removed safely. Report formatting repairs separately from retained source text.
- Include intermediate translations, validation stages and concrete document
  protection failures in issue reports to explain unexpected source retention.
- Use deterministic, collision-checked document and glossary marker prefixes;
  record `deterministic-prefix-v2` in new quality-report metadata. Derive mixed
  hexadecimal prefixes instead of the zero runs damaged in v1 model trials.

### Limitations

- Markdown parsing retains the document in memory to resolve reference links.
- Markdown extensions beyond the documented subset are not supported. Images,
  implicit reference labels and excluded HTML content remain untranslated.
- Embedded HTML processing is conservative: mismatched tags and unalignable
  container-prefixed HTML blocks are retained rather than repaired or rewritten.

## [0.1.0] - 2026-09-18

First release of the document translation library and CLI, focused on local
English-to-German translation of UTF-8 plain text.

### Added

- Importable reader, writer, and translation protocols with incremental document
  processing and a separate CLI interface.
- TXT paragraphs, simple bullet and numbered lists, wrapped list items, and
  conservative heading detection. Preserve source files, BOM, blank separators,
  list prefixes, and final line endings; reflow collapsed multiline translations.
- Local CUDA translation with pinned Marian (default) and selectable Qwen models.
  Optional local dependencies and CUDA 13.2 setup instructions; versioned Qwen
  prompts and explicit language validation.
- Sentence-sized model calls and token-aware splitting of oversized input.
  Recoverable failures retain original text with segment-linked JSONL reports;
  exit code 3 identifies a published, partially translated document.
- Optional JSON/gzip terminology glossaries with keep, translate, and annotate
  rules, prefix-trie matching, placeholder checks, sentence capitalization, and
  direct rendering of segments matching a complete glossary entry.
- A 36-entry example glossary with source notes, reusable synthetic evaluation
  inputs, manual quality reports, and an offline glossary benchmark.
- CLI progress with segment count, type, and elapsed time. Safe publication
  without overwriting existing output files; temporary-output cleanup on failure.
- Offline automated tests, a 90% package-coverage gate, clean-install checks,
  wheel/sdist verification, and GitHub release automation.

### Known limitations

- Markdown and ODP are not supported yet. The local backends require CUDA;
  automatic CPU fallback is not included. Marian supports only English to German.
- Translation still needs human review: terminology, grammar, and semantic
  omissions cannot be detected reliably by successful generation alone.
- TXT heading/sentence recognition is heuristic. Exact physical wrapping is not
  preserved, and some long lines remain. TXT has no reliable page numbering.
- Glossaries do not infer inflection, automatically recognize terminology, or
  track first mentions. Placeholder failures retain the entire source segment.
  Random placeholder identities can affect model output between runs.
- Processing is incremental between segments, but the current segment remains
  in memory. There is no resume support. Fatal model or file errors still abort;
  output publication requires filesystem hard-link support.

Release assets contain the wheel and source archive. Model weights, credentials,
private documents, and local measurement outputs are not bundled. No PyPI
publication is configured.
