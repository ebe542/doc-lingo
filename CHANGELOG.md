# Changelog

## [Unreleased]

### Fixed

- Reject overlapping local alignment proposals independently of evaluation order;
  retain evidence and identify conflicting scopes in experimental reports.

### Added

- Optional fixed-pair local alignment review with conservative anchor windows,
  independent proposals and explicit rejection diagnostics; production document
  translation remains unchanged.

### Changed

- Preserve formatting enclosing complete translation units using exact call
  boundaries; retain word-alignment checks for partially enclosed units.

- Align exact source-sentence translation calls separately before merging segment
  offsets; retain budget subdivision and conservative formatting validation.

- Organize tests by document format, translation, interfaces, scripts and
  integration responsibilities, retaining shared fixtures under `tests/fixtures`.

- Organize document adapters into `plain_text`, `markdown`, and `html` packages.
  Keep root library exports and Markdown adapter imports stable; separate
  Markdown readers/writers from shared parsing. Internal module imports move
  with their format packages. Standalone HTML translation is not added.

### Fixed

- Leave target-expansion headroom when planning awesome-align source chunks and
  bypass both models for standalone registered protection-marker units.

- Preserve scopes enclosing complete translated segments despite missing word
  links; include affected alignment-source positions in partial-scope diagnostics.

- Allow changed Markdown soft wraps in the alignment path without relaxing hard
  breaks, block structure, table cells or the legacy writer validation.

- Preserve Markdown block prefixes and outer whitespace outside aligned model
  input, and include attempted output and validation details in recovery reports.

- Allow translated prose to move around preserved Markdown inline elements.
  Keep checking nesting, nonempty inline containers, links and code contents.

### Added

- Separate aligned-path timing/call counters in CLI output, with source/target
  budget diagnostics and explicit missing/duplicate/unexpected marker identities.

- Long Markdown partial-formatting evaluation cases and deterministic coverage
  for nested scopes, independent links and localized missing correspondences.

- Budgeted source chunking for aligned translation, merging per-chunk character
  mappings before projecting Markdown/HTML formatting across chunk boundaries.

- Alignment-based HTML inline formatting and links inside Markdown, preserving
  exact tags and attributes and applying shared split/expansion/conflict rules.

- Opt-in Markdown alignment in the service and CLI with a local awesome-align
  model, reproducible writer validation and existing JSONL formatting warnings.

- Opt-in Markdown rendering of projected emphasis and links, retaining original
  wrappers and destinations, with nesting checks and parser-validated fallback.

- Bridge original formatting coordinates to model alignment and restored target
  text, with exact marker validation and existing translation-issue callbacks.

- Opt-in formatting projection: split optical styles, expand discontinuous
  links, drop unresolved scopes and overlapping links, and return structured
  diagnostics without changing translated text or the active document pipeline.

- Separate 30-case alignment evaluation suite covering longer paragraphs,
  repeated terms, registered markers and selected formatting scopes, with
  occurrence-specific review ranges and fixture consistency checks.

- Optional exact marker anchoring in alignment reports with raw results retained,
  plus configurable awesome-align threshold comparisons on registered fixtures.

- Opt-in exact content-marker alignment overrides conflicting statistical links;
  validate marker identities and mark affected surrounding prose as ambiguous.

- Optional awesome-align baseline using the same fixed pairs and pinned mBERT
  revision as SimAlign, with shared word-to-character alignment conversion.

- Optional SimAlign adapter and fixed-pair Argmax/IterMax evaluation with exact
  character ranges and encoder-length checks. Document alignment alternatives;
  real model compatibility and quality remain subject to local evaluation.

- Format-independent alignment protocol and validated many-to-many source/target
  ranges, including explicit unaligned and ambiguous source regions. No alignment
  algorithm or active translation integration is included.

- Opt-in token-budgeted model input units preserve source references and shared
  formatting ranges across splits. Content markers remain indivisible; oversized
  units use source-based recovery rather than exposing markers in retained text.

- Opt-in model-input preparation removes known wrappers and uses validated
  content markers for protected inline parts. Fully protected input bypasses
  model preparation; active translation and formatting alignment are unchanged.

- Source-backed translation input parts distinguish translatable text, removable
  wrappers and protected content. Preserve formatting relationships across
  sentences without changing the active translation service.

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
