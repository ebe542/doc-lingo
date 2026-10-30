"""Read and publish self-contained review archives without overwriting files."""

import json
import os
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from doc_lingo.documents.source_layout import SourceRange
from doc_lingo.review.jobs import ReviewBlock, ReviewJob, ReviewJobError
from doc_lingo.review.markdown import MarkdownSource

MAX_MEMBER_BYTES = 64 * 1024 * 1024


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReviewJobError("Duplicate JSON key in review job")
        result[key] = value
    return result


def save_job(job: ReviewJob, destination: str | Path) -> None:
    """Publish only a complete archive; preserve existing files and symlinks."""
    job.validate()
    destination = Path(destination)
    if os.path.lexists(destination):
        raise FileExistsError(f"Review job already exists: {destination}")
    metadata = asdict(job)
    del metadata["source"]
    if job.schema_version == 1:
        for block in metadata["blocks"]:
            del block["source_info"]
    encoded = (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if max(len(encoded), len(job.source)) > MAX_MEMBER_BYTES:
        raise ReviewJobError("Review job exceeds member size limit")
    with TemporaryDirectory(prefix=".doc-lingo-review-", dir=destination.parent) as directory:
        temporary = Path(directory) / "job.zip"
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("job.json", encoded)
            archive.writestr(f"source.{job.document_format}", job.source)
        os.link(temporary, destination)


def load_job(path: str | Path) -> ReviewJob:
    """Validate without extracting paths or loading any translation model."""
    try:
        with ZipFile(path) as archive:
            names = sorted(archive.namelist())
            if names not in (["job.json", "source.txt"], ["job.json", "source.md"]):
                raise ReviewJobError("Review archive must contain only job.json and its source")
            for member in archive.infolist():
                if member.file_size > MAX_MEMBER_BYTES:
                    raise ReviewJobError("Review job exceeds member size limit")
            metadata = json.loads(archive.read("job.json"), object_pairs_hook=_unique_object)
            if not isinstance(metadata, dict) or not isinstance(metadata.get("blocks"), list):
                raise ReviewJobError("Invalid review job metadata")
            if "source" in metadata:
                raise ReviewJobError("Source bytes must be stored separately")
            blocks = []
            for block in metadata.pop("blocks"):
                required = {"id", "type", "original", "proposal"}
                if metadata.get("schema_version") == 2:
                    required.add("source_info")
                if not isinstance(block, dict) or set(block) != required:
                    raise ReviewJobError("Missing or unknown review block fields")
                if "source_info" in block:
                    evidence = block["source_info"]
                    if not isinstance(evidence, dict) or set(evidence) != {
                        "start",
                        "end",
                        "formatting",
                        "protected",
                    }:
                        raise ReviewJobError("Invalid Markdown source evidence")
                    if not isinstance(evidence["formatting"], list) or not isinstance(
                        evidence["protected"], list
                    ):
                        raise ReviewJobError("Invalid Markdown source evidence arrays")
                    evidence["formatting"] = tuple(SourceRange(**r) for r in evidence["formatting"])
                    evidence["protected"] = tuple(evidence["protected"])
                    block["source_info"] = MarkdownSource(**evidence)
                blocks.append(ReviewBlock(**block))
            # All fields are mandatory in the stored schema, even those with API defaults.
            if set(metadata) != {
                "id",
                "source_name",
                "source_lang",
                "target_lang",
                "source_sha256",
                "schema_version",
                "document_format",
            }:
                raise ReviewJobError("Missing or unknown review metadata fields")
            if names[1] != f"source.{metadata['document_format']}":
                raise ReviewJobError("Review source member does not match document format")
            job = ReviewJob(source=archive.read(names[1]), blocks=tuple(blocks), **metadata)
            job.validate()
            return job
    except ReviewJobError:
        raise
    except (BadZipFile, UnicodeError, ValueError, TypeError, KeyError) as error:
        raise ReviewJobError("Invalid review job archive or metadata") from error
