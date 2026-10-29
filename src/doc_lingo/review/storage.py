"""Read and publish self-contained review archives without overwriting files."""

import json
import os
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from doc_lingo.review.jobs import ReviewBlock, ReviewJob, ReviewJobError

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
    encoded = (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if max(len(encoded), len(job.source)) > MAX_MEMBER_BYTES:
        raise ReviewJobError("Review job exceeds member size limit")
    with TemporaryDirectory(prefix=".doc-lingo-review-", dir=destination.parent) as directory:
        temporary = Path(directory) / "job.zip"
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("job.json", encoded)
            archive.writestr("source.txt", job.source)
        os.link(temporary, destination)


def load_job(path: str | Path) -> ReviewJob:
    """Validate without extracting paths or loading any translation model."""
    try:
        with ZipFile(path) as archive:
            if sorted(archive.namelist()) != ["job.json", "source.txt"]:
                raise ReviewJobError("Review archive must contain only job.json and source.txt")
            for member in archive.infolist():
                if member.file_size > MAX_MEMBER_BYTES:
                    raise ReviewJobError("Review job exceeds member size limit")
            metadata = json.loads(archive.read("job.json"), object_pairs_hook=_unique_object)
            if not isinstance(metadata, dict) or not isinstance(metadata.get("blocks"), list):
                raise ReviewJobError("Invalid review job metadata")
            if "source" in metadata:
                raise ReviewJobError("Source bytes must be stored separately")
            blocks = tuple(ReviewBlock(**block) for block in metadata.pop("blocks"))
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
            job = ReviewJob(source=archive.read("source.txt"), blocks=blocks, **metadata)
            job.validate()
            return job
    except (BadZipFile, UnicodeError, json.JSONDecodeError, TypeError, KeyError) as error:
        raise ReviewJobError("Invalid review job archive or metadata") from error
