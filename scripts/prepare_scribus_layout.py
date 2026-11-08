"""Prepare a portable export plan for scripts/import_scribus_layout.py."""

import argparse
import sys
from pathlib import Path

from doc_lingo.pdf_layout.scribus_plan import prepare_scribus


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    for name in ("layout", "groups", "font-map", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = prepare_scribus(args.source, args.layout, args.groups, args.font_map, args.output)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print(f"Scribus preparation failed: {error}", file=sys.stderr)
        return 1
    print(f"Scribus plan complete: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
