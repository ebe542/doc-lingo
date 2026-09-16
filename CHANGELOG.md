# Changelog

## [Unreleased]

### Changed

- Default the CLI and quality runner to Marian, retain explicit Qwen selection,
  and reject unsupported language pairs before runtime loading or output creation.

- Translation system prompt v2 strengthens meaning preservation, German grammar,
  and technical abbreviation handling; model and decoding settings are unchanged.

- Organize code into interfaces, translation, and document packages while
  preserving public imports from `doc_lingo`.

### Added

- Continue CLI translation after recoverable text-unit failures, retaining source
  text with segment-linked JSONL diagnostics and partial-success exit code 3.

- Conservative TXT heading detection, reflow of collapsed multiline translations,
  and sentence-sized model calls independent of maximum context capacity.

- Token-aware splitting of oversized segments for Marian and Qwen, preferring
  sentence boundaries and retaining one document segment with atomic output.

- Lazy CUDA Marian backend for English-to-German translation and backend selection
  in the quality runner, with separate model and generation metadata.

- Ten English/German translation quality examples and manual criteria, including
  technical abbreviations and document-wide terminology consistency.
- Quality evaluation runner with persistent manual-review reports and offline
  tests for document processing, failures, and temporary-file cleanup.

- Simple TXT list segments with preserved bullet/number prefixes, indentation,
  and shared reader/writer boundaries.
- Wrapped list items remain a single translation segment through the next marker,
  blank line, or end of file.
- Segment types retained during translation and displayed in CLI progress;
  progress callbacks now receive both count and type.

- CLI paragraph progress and elapsed time via an optional library callback.

- CLI TXT translation with default or explicit output paths and expected-error
  messages on stderr with nonzero exit codes.

- Optional local CUDA backend with a pinned Qwen3-1.7B revision, versioned prompts,
  explicit token limits, and CUDA 13.2 setup instructions.

- Translation backend protocol, TranslationError, and lazy document translation
  orchestration with preserved segment IDs and managed reading sessions.

- Document writer protocol and TXT reconstruction with segment validation,
  formatting preservation, and publication without overwriting existing files.

- Shared document reader protocol, immutable text segments, and incremental
  UTF-8 paragraph extraction with explicit resource management.

- Initial doc-lingo package and CLI help/version interface.
- Quality and GitHub release workflows with package installation checks.
- Git Bash development instructions and a format roadmap: TXT, Markdown, then ODP.

Markdown, ODP, and optional file logging are still planned.
