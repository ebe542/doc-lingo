# Changelog

## [Unreleased]

### Added

- Persistent TXT review jobs through `doc_lingo.review`, with source snapshots,
  ordered translation proposals, versioned metadata and source/inventory validation.
  Archive publication refuses existing files. ODT review export/import is still planned.

### Documentation

- Define the planned editable ODT review workflow, four-row block layout,
  correction selection, persistent job identity and staged TXT-first implementation.
  Review import/finalization and PDF support are not implemented yet.

### Fixed

- Preserve complete ODT paragraph styles after unwrapped leading soft page breaks
  without sending those boundary elements to the model. Partial scopes still
  require alignment evidence. Omit plain whitespace-only optical scopes without
  warning; retain explicit whitespace elements and link validation.

## [0.3.0] - 2026-10-27

OpenDocument text (ODT) support joins TXT and Markdown in the library and CLI.
ODT is a conservative subset; translated text can change wrapping and pagination.

### Added

- ODT package inspection and readers/writers for headings, paragraphs, lists,
  textual table cells, supported textboxes/captions and headers/footers, including
  left/first-page variants. Preserve XML structure, images and package payloads
  outside edited text; reject unsupported or damaged package structures.
- Optional awesome-align formatting projection for ODT. Hide style/link syntax
  from model input, split optical styles, expand links and report uncertain scopes.
  Without alignment, inline XML uses conservative marker protection.
- Independent nested textbox translation and recovery. Patch `content.xml` and
  `styles.xml` with part-qualified IDs while preserving page templates and fields.
- ODT CLI progress and JSONL diagnostics for retained text, dropped formatting and
  unsupported text. Published outputs with warnings return exit code 3.
- Reproducible ODT review tooling with source/output hashes, package preservation
  checks, model metadata and inventories. Report version 2 includes header/footer
  paragraphs in totals; `peripheral_text` is a filtered view of the same blocks.
- Installed-wheel ODT translation smoke check without model dependencies.

### Fixed

- Protect recognized preformatted paragraph styles and inherited styles, including
  code comments and indentation. Preserve cells with formulas or stored values.
- Exclude verified language-only styles from optical formatting projection and
  preserve eligible leading image anchors outside model input.
- Bypass models for field-only paragraphs with whitespace/separators, such as
  page-number/count footers, without producing unnecessary recovery warnings.

### Documentation

- Correct OpenDocument terminology: the intended format is ODT text documents,
  not ODP presentations. Document supported scope, review evidence and limitations.

### Known limitations

- Unsupported containers/inline content remain unchanged with diagnostics.
  Text in images and image descriptions is not translated. Preformatted protection
  depends on recognized styles; arbitrary unmarked code is not detected.
- Alignment may drop uncertain style/link scopes while retaining translated text.
  The reviewed six-page sample has ten remaining formatting warnings; this is
  sample-specific evidence, not a general quality guarantee.
- No guarantee of identical pagination, textbox fit or linguistic correctness.
  XML and block indexes are held in memory; no resume support is provided.
  Metadata statistics, thumbnails and document language are not recalculated.
- Local model/alignment dependencies remain optional. Package checks do not verify
  GPU compatibility; existing TXT/Markdown limitations still apply.

## [0.2.0] - 2026-10-10

Markdown translation and optional alignment-based formatting, building on the
TXT workflow introduced in 0.1.0. Local alignment repair remains an evaluation
experiment and is not enabled in document translation.

### Added

- Markdown readers, writers and CLI format selection, including headings, lists,
  block quotes, table cells and supported embedded HTML text. Preserve code,
  destinations, attributes, excluded content and source structure conservatively.
- Optional awesome-align integration through `--aligner awesome` and a caller-owned
  local checkpoint. Formatting projection supports split emphasis, expanded links,
  nested styles and exact protected-marker validation.
- Exact translation-unit boundaries and sentence-paired alignment with token-budget
  subdivision, target-expansion headroom and global character-coordinate merging.
- Structured JSONL recovery and formatting diagnostics, plus aligned-path timing
  and call statistics. Exit code 3 covers published outputs with formatting warnings
  as well as retained source text.
- Reproducible alignment comparisons, SimAlign/awesome-align adapters, fixed-pair
  suites and real-model review guides. Experimental local review records independent
  proposals and rejects overlapping windows; manual review remains required.

### Changed

- Organize document adapters by format and tests by responsibility. Public root
  library exports remain available; internal adapter import paths have changed.
- Use deterministic collision-checked protection markers. Preserve complete-unit
  formatting without inventing word links; keep strict checks at partial boundaries.

### Fixed

- Preserve Markdown block prefixes and outer whitespace outside model input, while
  allowing translated soft wraps without weakening structural validation.
- Bypass models for standalone registered marker units and retain diagnostic
  evidence for encoder overflow, invalid markers and rejected formatting.
- Ignore whitespace-only uncertainty remaining between complete translation units.

### Known limitations

- Markdown is a documented subset, not full GitHub Flavored Markdown. Images and
  implicit reference labels remain untranslated; relative links and heading-fragment
  destinations are not rewritten. ODT and standalone HTML files are not supported.
- Markdown parsing retains the source document in memory. Sentence recognition is
  heuristic; there is no resume support or guaranteed text-layout equivalence.
- Partial formatting can be dropped when words are omitted, repeated ambiguously
  or combined into one translated word. Links may expand over intervening text;
  inspect diagnostics and rendered output. Successful fixtures do not prove general
  linguistic accuracy, including for the experimental local-review proposals.
- Local translation still requires CUDA. Optional alignment requires its own extra
  and model files. Model weights, credentials and private reports are not bundled.
- Existing output files are never overwritten; publication requires filesystem
  hard-link support. Fatal file/model errors can still abort processing.

Release assets are a wheel and source archive on GitHub; no PyPI publication is
configured. Evaluation scripts are provided in the source archive, not as public
library APIs in the wheel.

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

- Markdown and ODT are not supported yet. The local backends require CUDA;
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
