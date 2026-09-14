"""Shared contracts for reading translatable document segments."""

from collections.abc import Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TextSegment:
    """Text with an opaque ID, unique and repeatable within an unchanged document."""

    id: str
    text: str


class DocumentReader(Protocol):
    """Provide ordered segments within an explicitly managed resource lifetime.

    Consume the iterator only inside its context. Exiting the context releases
    resources even after early termination or an exception. Each call creates
    an independent reading session. Adapters need not inherit this protocol.
    """

    def iter_segments(self) -> AbstractContextManager[Iterator[TextSegment]]:
        """Open a reading session; IDs remain stable while the source is unchanged."""
        ...
