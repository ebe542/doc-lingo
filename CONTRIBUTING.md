# Contributing to doc-lingo

Read the [developer guide](docs/development.md) for the agreed collaboration
workflow, library/CLI architecture, commit boundaries, and temporary-file cleanup.
The maintainer writes and runs tests and creates commits; the assistant supplies
Git Bash commands and discusses every commit before implementation and creation.

Use English for code, comments, documentation, and CLI messages.
Develop in small, explained steps. Keep document handling separate from the
translation backend so additional formats can reuse translation logic.
Implement document support in order: plain text (`.txt`), Markdown (`.md`), then
OpenDocument presentations (`.odp`). See the developer guide for the format roadmap.

## Local workflow

Use Git Bash on Windows and Python 3.11–3.13. After following the README setup:

```bash
source .venv/Scripts/activate
python -m ruff format . && python scripts/check_milestone.py
```

Write tests for observable behavior, especially document preservation and error
handling. Automated tests must not require secrets, paid APIs, or model downloads.
Use synthetic documents for fixtures. Never overwrite real source documents in tests.

For a clean CI-equivalent installation using the active Python interpreter:

```bash
python scripts/check_ci_environment.py
```

Use focused Conventional Commits, such as `chore: adapt doc-lingo project scaffold`.
The solo-maintainer workflow uses `main`. Inspect changes before committing.

## GitHub Actions

The quality workflow runs the shared gate on Python 3.11, 3.12, and 3.13 for
pushes to `main`, pull requests, and manual runs. Shell steps use Bash.

The release workflow accepts annotated `vX.Y.Z` tags (also `aN`, `bN`, or `rcN`
suffixes). The tagged commit must belong to `main`, its package version must match
the tag, and `CHANGELOG.md` must contain a matching dated release section.
It checks quality, tests wheel installation and the CLI, then publishes wheel and
source archives to a GitHub release. It does not publish to PyPI.

Before releasing, move the relevant Unreleased notes to a dated heading such as
`## [0.1.0] - YYYY-MM-DD`, using the actual release date, and verify:

```bash
python scripts/check_milestone.py && python scripts/check_release_package.py
```

Commit and push reviewed changes, then confirm GitHub Actions succeeds before
creating and pushing a release tag. A local check alone does not verify CI.

For the prepared 0.1.0 release, first install release tooling if needed and run
the package check (the script builds and installs into disposable storage):

```bash
python -m pip install -e ".[dev,release]"
python scripts/check_milestone.py
python scripts/check_release_package.py
```

The dated changelog section must use the actual release date; update it if the
release is postponed. After reviewing, committing and pushing the release notes,
wait for green quality CI on that commit. From a clean, up-to-date `main`, create
an annotated tag and publish that tag explicitly:

```bash
git status --short
git tag -a v0.1.0 -m "Release 0.1.0"
git push origin v0.1.0
```

Pushing the tag starts the release workflow and publishes the GitHub release
automatically after verification. Do not move or overwrite an existing release
tag. Confirm the Release workflow succeeds and the wheel and source archive are
attached. The source archive contains documentation and examples; the wheel
contains the importable package and CLI, not the repository's example files.
