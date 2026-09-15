# Changelog

## [Unreleased]

### Changed

- Organize code into interfaces, translation, and document packages while
  preserving public imports from `doc_lingo`.

### Added

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
