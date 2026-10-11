# Release preparation: 0.2.0

Status: prepared, not published. Intended scope is TXT and Markdown translation
with opt-in awesome-align formatting. ODT is deferred. Local alignment review
remains an experimental source-distribution tool and is not integrated into the
document CLI. See the dated changelog for user-facing notes.

## Evidence and outstanding checks

- The maintainer reported green workflows for the preceding implementation commits.
- Markdown long-scope run 05 restored the five inspected scopes without warnings.
- Inline examples document both successful projection and conservative drops.
- Local-review experiments demonstrate selected useful proposals, safe rejections,
  and the limitation of consistently wrong repeated anchors. They do not establish
  general linguistic correctness or justify automatic repairs.
- The release-preparation changes still require the checks below. No release tag
  or publication has been created during preparation.

## Maintainer commands

Run from the repository root in Git Bash. Refresh editable metadata after the
version change, then run the quality and clean package checks:

```bash
python -m pip install -e ".[dev,release]" &&
python -m scripts.check_milestone &&
python -m scripts.check_release_package
```

The package check builds wheel/sdist, checks their metadata and installs the wheel
in a temporary clean environment. It checks the CLI and runs a model-free TXT and
Markdown library smoke check. It does not prove optional CUDA/model compatibility.
Its temporary directory is context-managed. Follow the development guide for
cleanup of the maintainer-created pytest temporary directory.

After successful checks, review and commit the preparation changes, push main,
and confirm green CI. Proposed commit subject: `chore: prepare 0.2.0 Markdown release`.
If publication occurs on another date, update the changelog date before that commit.

Only after confirming that exact committed state and agreeing to publication:

```bash
git tag -a v0.2.0 -m "Release 0.2.0" &&
git push origin v0.2.0
```

The tag must be annotated, match package metadata and the dated changelog, and
refer to a commit on main. Pushing it triggers the existing workflow, which
verifies, builds and publishes GitHub release assets. These commands are a later
maintainer step, not actions performed by the assistant. No PyPI upload is configured.
