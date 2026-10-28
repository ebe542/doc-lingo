"""Build and verify installable release distributions in temporary storage."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DISTRIBUTION_NAME = "doc-lingo"

# Executed by the clean environment's interpreter against the installed wheel.
ODT_SMOKE = """
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZIP_STORED
from doc_lingo import translate_document
from doc_lingo.documents.odt import OdtReader, OdtWriter, inspect_package

office = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
text = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
style = "urn:oasis:names:tc:opendocument:xmlns:style:1.0"
manifest = "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
mime = b"application/vnd.oasis.opendocument.text"
content = (f'<o:document-content xmlns:o="{office}" xmlns:t="{text}">'
    '<o:body><o:text><t:h t:outline-level="1">Hello</t:h>'
    '<t:p><t:span>Hello</t:span></t:p></o:text></o:body>'
    '</o:document-content>').encode()
styles = (f'<o:document-styles xmlns:o="{office}" xmlns:t="{text}" xmlns:s="{style}">'
    '<o:master-styles><s:master-page s:name="Standard"><s:header>'
    '<t:p>Hello</t:p></s:header><s:footer><t:p><t:page-number>1</t:page-number>'
    '/ <t:page-count>1</t:page-count></t:p></s:footer>'
    '</s:master-page></o:master-styles></o:document-styles>').encode()
manifest_xml = (f'<m:manifest xmlns:m="{manifest}">'
    f'<m:file-entry m:full-path="/" m:media-type="{mime.decode()}"/>'
    '<m:file-entry m:full-path="content.xml" m:media-type="text/xml"/>'
    '<m:file-entry m:full-path="styles.xml" m:media-type="text/xml"/>'
    '</m:manifest>').encode()

class Backend:
    def translate(self, text, **kwargs):
        assert text == "Hello", text
        return "Hallo"

with TemporaryDirectory(prefix="doc-lingo-odt-smoke-") as directory:
    source = Path(directory) / "source.odt"
    target = Path(directory) / "target.odt"
    members = {"mimetype": mime, "content.xml": content, "styles.xml": styles,
        "META-INF/manifest.xml": manifest_xml}
    with ZipFile(source, "w", compression=ZIP_STORED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    translate_document(OdtReader(source), OdtWriter(source), Backend(), target,
        source_lang="en", target_lang="de")
    inspect_package(target)
    with ZipFile(target) as archive:
        assert archive.namelist() == list(members)
        for name, payload in members.items():
            expected = payload.replace(b">Hello<", b">Hallo<")
            assert archive.read(name) == expected, name
"""


def project_version() -> str:
    """Read the single release version declared in project metadata."""

    configuration = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(configuration["project"]["version"])


def environment_python(environment: Path) -> Path:
    """Return the virtual-environment interpreter on every supported platform."""

    if os.name == "nt":
        return environment / "Scripts" / "python.exe"
    return environment / "bin" / "python"


def run(command: list[str]) -> None:
    """Run one visible packaging command from the project root."""

    print(f"\n> {' '.join(command)}", flush=True)
    subprocess.run(command, check=True, cwd=PROJECT_ROOT)


def find_distribution(distribution_directory: Path, suffix: str) -> Path:
    """Require exactly one newly built distribution with the requested suffix."""

    matches = sorted(distribution_directory.glob(f"*{suffix}"))
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one {suffix} distribution, found {len(matches)}")
    return matches[0]


def build_parser() -> argparse.ArgumentParser:
    """Build arguments for selecting the clean-environment interpreter."""

    parser = argparse.ArgumentParser(
        description="Build, inspect, and install the release package in a clean environment",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python interpreter used to create the clean environment (default: active Python)",
    )
    return parser


def main() -> None:
    """Build wheel and sdist, validate metadata, and smoke-test the wheel."""

    args = build_parser().parse_args()
    expected_version = project_version()
    with tempfile.TemporaryDirectory(prefix="doc-lingo-release-") as directory:
        temporary_root = Path(directory)
        distribution_directory = temporary_root / "dist"
        environment = temporary_root / "venv"

        run(
            [
                sys.executable,
                "-m",
                "build",
                "--outdir",
                str(distribution_directory),
                ".",
            ]
        )
        wheel = find_distribution(distribution_directory, ".whl")
        source_distribution = find_distribution(distribution_directory, ".tar.gz")
        run(
            [
                sys.executable,
                "-m",
                "twine",
                "check",
                str(wheel),
                str(source_distribution),
            ]
        )

        run([args.python, "-m", "venv", str(environment)])
        python = environment_python(environment)
        run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                str(wheel),
            ]
        )
        run(
            [
                str(python),
                "-c",
                (
                    "from importlib.metadata import version; "
                    f"assert version('{DISTRIBUTION_NAME}') == '{expected_version}'"
                ),
            ]
        )
        run([str(python), "-m", "doc_lingo.interfaces.cli", "--version"])
        run([str(python), "-m", "doc_lingo.interfaces.cli", "--help"])
        executable = python.parent / ("doc-lingo.exe" if os.name == "nt" else "doc-lingo")
        run([str(executable), "--help"])
        run(
            [
                str(python),
                "-c",
                "from pathlib import Path\n"
                "from tempfile import TemporaryDirectory\n"
                "from doc_lingo import (PlainTextReader, PlainTextWriter, "
                "MarkdownReader, MarkdownWriter, translate_document)\n"
                "class Echo:\n"
                "    def translate(self, text, *, source_lang, target_lang):\n"
                "        return text\n"
                "with TemporaryDirectory(prefix='doc-lingo-smoke-') as directory:\n"
                "    root = Path(directory)\n"
                "    for suffix, reader, writer, text in (\n"
                "        ('txt', PlainTextReader, PlainTextWriter, 'Hello world.\\n'),\n"
                "        ('md', MarkdownReader, MarkdownWriter, "
                "'# Heading\\n\\nRead **this** [guide](https://example.org).\\n'),\n"
                "    ):\n"
                "        source = root / ('source.' + suffix)\n"
                "        target = root / ('target.' + suffix)\n"
                "        source.write_text(text, encoding='utf-8', newline='\\n')\n"
                "        translate_document(reader(source), writer(source), Echo(), target, "
                "source_lang='en', target_lang='de')\n"
                "        assert target.read_bytes() == source.read_bytes(), suffix\n",
            ]
        )

        run([str(python), "-c", ODT_SMOKE])

    print("\nRelease package checks passed.")


if __name__ == "__main__":
    main()
