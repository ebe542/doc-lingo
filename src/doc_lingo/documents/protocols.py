"""Shared contracts for reading translatable document segments."""

from collections.abc import Iterable, Iterator
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol

from doc_lingo.documents.models import TextSegment


class DocumentReader(Protocol):
    """Provide ordered segments within an explicitly managed resource lifetime.

    Consume the iterator only inside its context. Exiting the context releases
    resources even after early termination or an exception. Each call creates
    an independent reading session. Adapters need not inherit this protocol.
    """

    def iter_segments(self) -> AbstractContextManager[Iterator[TextSegment]]:
        """Open a reading session; IDs remain stable while the source is unchanged."""
        ...


class DocumentWriter(Protocol):
    """Write ordered translations into the unchanged original document structure.

    Implementations own their file resources, but not the supplied iterable.
    Missing, extra, or out-of-order IDs raise SegmentMismatchError. Existing
    destinations must never be replaced. No output is published before validation.
    """

    def write(self, destination: Path, translations: Iterable[TextSegment]) -> None:
        """Write a separate result; propagate encoding, input, and I/O failures."""
        ...
