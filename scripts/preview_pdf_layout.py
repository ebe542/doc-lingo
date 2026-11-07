"""Create an offline visual inspection of extracted PDF geometry."""

import argparse
import sys
from pathlib import Path

from doc_lingo.pdf_layout.preview import create_preview


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--layout", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--groups", type=Path, help="Optional derived text-group directory")
    args = parser.parse_args(argv)
    try:
        result = create_preview(args.source, args.layout, args.output, groups=args.groups)
    except (OSError, ValueError, RuntimeError, ImportError, KeyError) as error:
        print(f"PDF preview failed: {error}", file=sys.stderr)
        return 1
    print(f"PDF preview complete: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
