"""Inspect local PDF font availability and explicit font choices."""

import argparse
import sys
from pathlib import Path

from doc_lingo.pdf_layout.fonts import font_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("layout", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--font-dir",
        action="append",
        type=Path,
        help="Search this directory instead of defaults; repeat for multiple locations",
    )
    parser.add_argument("--mapping", type=Path)
    args = parser.parse_args(argv)
    try:
        result = font_report(
            args.layout, args.output, directories=args.font_dir, mapping=args.mapping
        )
    except (OSError, ValueError, RuntimeError, ImportError, KeyError) as error:
        print(f"PDF font check failed: {error}", file=sys.stderr)
        return 1
    print(f"PDF font report complete: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
