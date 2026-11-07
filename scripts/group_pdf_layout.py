"""Derive reviewable text groups from existing PDF extraction JSON."""

import argparse
import sys
from pathlib import Path

from doc_lingo.pdf_layout.grouping import group_layout


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("layout", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = group_layout(args.layout, args.output)
    except (OSError, ValueError, KeyError) as error:
        print(f"PDF grouping failed: {error}", file=sys.stderr)
        return 1
    print(f"PDF grouping complete: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
