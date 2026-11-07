"""Export PDF evidence without loading a translator."""

import argparse
import sys
from pathlib import Path

from doc_lingo.pdf_layout import extract_layout


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--pages", type=int, nargs="+", help="1-based PDF page numbers")
    parser.add_argument(
        "--export-fonts",
        action="store_true",
        help="Export embedded font bytes only when you have the necessary rights",
    )
    args = parser.parse_args(argv)
    try:
        manifest = extract_layout(
            args.source,
            args.output,
            pages=tuple(args.pages) if args.pages is not None else None,
            export_fonts=args.export_fonts,
        )
    except (OSError, ValueError, RuntimeError) as error:
        print(f"PDF extraction failed: {error}", file=sys.stderr)
        return 1
    print(f"PDF layout extraction complete: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
