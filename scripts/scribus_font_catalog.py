"""Run inside Scribus via Script > Execute Script; requires only its standard library."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile


def export_catalog(scribus, destination):
    """Capture names accepted by Scribus without changing an open document."""
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    available = set(scribus.getFontNames())
    fonts = []
    for row in scribus.getXFontNames():
        if len(row) != 6:
            raise ValueError("Unexpected Scribus font metadata format")
        name, family, postscript, subset, embed_ps, file = row
        if name not in available:
            continue
        fonts.append(
            {
                "scribus_name": name,
                "family": family,
                "postscript_name": postscript,
                "file": file,
                "scribus_subset_setting": bool(subset),
                "scribus_embed_ps_setting": bool(embed_ps),
            }
        )
    # Keep available names even when extended metadata is absent.
    known = {font["scribus_name"] for font in fonts}
    for name in sorted(available - known):
        fonts.append(
            {
                "scribus_name": name,
                "family": None,
                "postscript_name": None,
                "file": None,
                "scribus_subset_setting": None,
                "scribus_embed_ps_setting": None,
            }
        )
    data = {
        "schema_version": 1,
        "kind": "scribus_font_catalog",
        "scribus_version": str(getattr(scribus, "scribus_version", "unknown")),
        "created_utc": datetime.now(timezone.utc).isoformat(),  # noqa: UP017 - Scribus uses Python 3.8
        "fonts": sorted(fonts, key=lambda font: font["scribus_name"]),
        "notes": [
            "Snapshot of available Scribus font names, not a glyph or metric validation.",
            "Scribus subset/export settings are not evidence of an embedded PDF font subset.",
        ],
    }
    temporary = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            suffix=".json",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink()
    return len(fonts)


def main():
    try:
        import scribus
    except ImportError:
        print("Run this script inside Scribus: Script > Execute Script.")
        return 1
    filename = scribus.fileDialog(
        "Export available Scribus fonts",
        "JSON (*.json)",
        defaultname="scribus-fonts.json",
        issave=True,
    )
    if not filename:
        return 0
    try:
        count = export_catalog(scribus, filename)
    except (OSError, ValueError) as error:
        scribus.messageBox("Font catalog failed", str(error))
        return 1
    scribus.messageBox("Font catalog complete", f"{count} font names saved to:\n{filename}")
    return 0


if __name__ == "__main__":
    main()
