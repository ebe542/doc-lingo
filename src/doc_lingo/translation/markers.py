"""Stable, source-disjoint namespaces for temporary protection markers."""

from hashlib import sha256
from typing import Literal

MARKER_POLICY = "deterministic-prefix-v2"


def marker_prefix(text: str, *, namespace: Literal["DLM", "DLG"]) -> str:
    """Choose the first unused prefix, independently of calls or process state.

    Retain the previous 32-hex-character shape to isolate reproducibility from
    marker-length changes. Hashing the namespace and collision counter avoids
    zero-padded counters: Marian changed their long zero runs in both recorded
    stable-marker trials. This does not guarantee model copying accuracy.
    Checking the entire prefix also excludes partial
    marker-like source strings. Case-insensitive matching is conservative when
    models change the case of surrounding source text. This is not a secret or
    a security token; restoration still validates every returned marker.
    """
    folded = text.lower()
    counter = 0
    while True:
        digest = sha256(f"{namespace}:{counter}".encode("ascii")).hexdigest()[:32].upper()
        candidate = namespace + digest
        if candidate.lower() not in folded:
            return candidate
        counter += 1
