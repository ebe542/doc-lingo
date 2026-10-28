# Release preparation: 0.3.0

Status: prepared, not published. ODT support joins TXT and Markdown. The library
and CLI translate supported body paragraphs, lists, textual tables, textboxes,
captions and headers/footers. Optional awesome-align projects formatting; the
default path protects inline XML with markers. See [ODT scope](odt.md) and the
[dated release notes](../CHANGELOG.md#030---2026-10-27) for limitations.

## Evidence and outstanding checks

- The maintainer reported successful milestone checks and green CI for the
  completed ODT implementation, including headers/footers and field-only bypass.
- Local `run-07` completed with 87 processed segments, 17 skipped blocks and ten
  existing formatting warnings. No source-retention warnings or alignment failures
  remained. The field-only footer was correctly inventoried as `protected_only`.
- The maintainer confirmed successful visual review. The generated report retains
  `manual_review: pending`; the confirmation is recorded separately here.
- The ten warnings represent conservative style/link drops, not a complete
  formatting match. One reviewed document does not establish general translation
  quality, layout equivalence or compatibility with every ODT producer.
- The release-preparation changes, including the installed-wheel ODT smoke check,
  still require the checks below. No tag or publication is part of preparation.

## Maintainer commands

From the repository root in Git Bash, refresh editable package metadata and run:

```bash
python -m pip install -e ".[dev,release]" &&
python -m scripts.check_milestone &&
python -m scripts.check_release_package
```

The package check builds wheel/sdist, checks metadata and installs the wheel in a
temporary clean environment. CLI checks and TXT/Markdown/ODT library smoke checks
do not load models. The ODT check translates body/header text with a deterministic
backend and checks exact XML, field preservation and package members. It does not
replace GPU/model runs or editor review. Temporary directories are context-managed.

Review and commit preparation as `chore: prepare 0.3.0 ODT release`, push main, and
wait for green CI on that commit. If publication is postponed, update the changelog
date and links before committing. Do not tag an unverified or dirty checkout.

After the exact committed state is verified and publication is agreed:

```bash
git status --short
git tag -a v0.3.0 -m "Release 0.3.0" &&
git push origin v0.3.0
```

The annotated tag must match package metadata and the dated changelog and belong
to main. Pushing it triggers verification and publication of GitHub wheel/sdist
assets. No PyPI publication is configured. Do not move an existing release tag.
Confirm the Release workflow and attached assets after publication.
