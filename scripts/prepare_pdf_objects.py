"""Build an inspectable PDF object/flow plan without translation or rendering."""

import argparse
import sys
from pathlib import Path

from doc_lingo.pdf_layout.protected_objects import build_object_plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("layout", type=Path)
    parser.add_argument("--assignments", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = build_object_plan(args.layout, args.assignments, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"PDF object preparation failed: {error}", file=sys.stderr)
        return 1
    print(f"PDF object plan complete: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
