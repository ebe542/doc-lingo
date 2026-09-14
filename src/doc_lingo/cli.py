"""Command-line interface for doc-lingo."""

from __future__ import annotations

import argparse
from importlib.metadata import version
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    """Describe the planned translation interface without modifying documents."""
    parser = argparse.ArgumentParser(
        prog="doc-lingo",
        description="Translate documents while preserving formatting (translation coming soon).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {version('doc-lingo')}")
    parser.add_argument("file", type=Path, help="Source document (initial format: .odp)")
    parser.add_argument("--target-lang", required=True, help="Target language code, for example de")
    return parser


def main(argv: list[str] | None = None) -> None:
    """Expose the CLI contract; fail explicitly until translation is implemented."""
    parser = build_parser()
    parser.parse_args(argv)
    parser.error("Document translation is not implemented yet. No files were changed.")


if __name__ == "__main__":
    main()
