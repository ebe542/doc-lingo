# Developer guide

## Working agreement

This is a productive learning project. Discuss each proposed commit with the
maintainer before implementing its changes: explain its purpose, scope, expected
behavior, and validation steps. Agree on one small, coherent step at a time.

- Every commit must leave the project installable and executable. Do not commit
  broken intermediate states or advertise unfinished behavior as available.
- Keep commits focused and small enough to review and understand independently.
  Documentation-only changes must preserve the runnable state of the project.
- The maintainer writes the tests, runs validation, and creates commits. The
  assistant explains the expected checks and supplies Git Bash commands; it does
  not write or run tests, stage changes, commit, push, or tag on their behalf.
- Discuss each commit before it is created, including its exact files and a
  proposed Conventional Commit message. Avoid blanket staging commands.
- Create releases at agreed, useful milestones, not after every commit. Discuss
  the release scope and version before the maintainer creates a tag.
- Use English for project artifacts and German for collaboration.

An explicit request to edit an agreed document authorizes that documentation
change. It does not authorize creating a Git commit.

## Library and CLI architecture

Publish one Python distribution, `doc-lingo`, containing both an importable
`doc_lingo` library and the `doc-lingo` command-line entry point. Other Python
applications must be able to use translation without invoking the CLI.

Build toward these responsibilities incrementally; this is a design target,
not a claim that translation is already implemented:

| Component | Responsibility |
| --- | --- |
| Public library API | Accept explicit translation options and return structured results. |
| Translation service | Coordinate document reading, text translation, and output writing. |
| Document adapters | Handle format-specific content and formatting, starting with plain text. |
| Translation backends | Translate text independently of document formats. |
| CLI | Parse arguments, resolve configuration, call the library, and render results. |

The CLI depends on the library; the library must not depend on the CLI. Keep
argument parsing, terminal output, and process exit codes at the CLI boundary.
Library operations return values or raise documented exceptions. Importing the
library must not load models, read `.env`, contact services, or modify files.

Pass configuration and backend dependencies explicitly to library operations.
Keep credential loading at the application boundary. Decide on the public API
in a dedicated commit discussion before adding it; the current package provides
only the CLI scaffold.

Keep originals intact and write a separate result for every supported format.
The shared translation service must not assume slides, XML, or any particular
document format. Format-specific extraction and reconstruction belong in adapters.

## Format implementation roadmap

Implement support in the order **TXT, Markdown, then ODP**. Each stage builds on
the same public library API and translation backend and is exposed through the CLI.
The roadmap describes planned behavior; the current scaffold does not translate files.

1. **Plain text (`.txt`):** establish reading, translation, and separate output
   writing with English-to-German translation first. Preserve paragraph structure.
   Agree on encoding handling and output naming before implementation.
2. **Markdown (`.md`):** translate prose while preserving headings, lists, emphasis,
   code blocks, and link destinations. Define which text elements are translatable
   and how structure is retained before implementing the adapter.
3. **OpenDocument presentations (`.odp`):** preserve document structure, styles,
   images, and non-text content while changing translatable text. Longer translations
   may overflow existing text boxes; validate layout fit separately from formatting.

Split each stage into small, runnable commits using the working agreement above.
A usable TXT implementation can be a release milestone before Markdown or ODP
support exists; discuss release readiness and limitations with the maintainer.

## Commit and validation sequence

1. Discuss a single behavior or improvement and agree on its boundaries.
2. Implement the agreed production changes and explain the relevant design.
3. The maintainer writes appropriate tests and runs the supplied commands.
4. Review the diff, validation results, and exact staging list together.
5. The maintainer commits and pushes; verify the GitHub Actions result.

Run commands from the project root in Git Bash after activating the environment:

```bash
source .venv/Scripts/activate
python scripts/check_milestone.py
```

The shared gate checks formatting, lint, tests, coverage, and Git whitespace.
The assistant provides specific test and commit commands for each agreed step.
Tests must use synthetic documents and avoid secrets or online model services.

## Temporary files and directories

Remove every task-created temporary directory when the task is finished,
including after failures. Track which paths the task created and check their
resolved locations before cleanup. Never delete pre-existing or user-owned data.
Prefer context-managed temporary directories in tooling so cleanup is automatic.

The current quality command uses `.pytest-tmp`; the person running it must remove
that temporary directory after the check, including after a failed run. The
assistant must clean up its own temporary directories before handing work back.
A reusable `.venv` is a development environment, not a disposable task directory.

## Releases

A release represents a coherent, usable capability with documented limitations.
Agree on the milestone and version, update package metadata and dated changelog
notes, then have the maintainer run quality and package installation checks.
Commit and push the reviewed state and confirm green CI before tagging it.

The existing workflow builds and publishes GitHub release assets from annotated
version tags. See [CONTRIBUTING.md](../CONTRIBUTING.md) for its requirements.
An initial scaffold release must clearly state that translation is unavailable.
