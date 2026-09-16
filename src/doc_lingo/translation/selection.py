"""Shared application defaults and language validation for local backends."""

DEFAULT_BACKEND = "marian"
BACKEND_NAMES = ("marian", "qwen")


def validate_language_pair(backend: str, source_lang: str, target_lang: str) -> None:
    """Reject unsupported requests before model loading or output creation.

    Backend implementations still validate direct library calls themselves.
    Qwen retains same-language passthrough for compatibility.
    """
    if backend not in BACKEND_NAMES:
        raise ValueError(f"Unknown backend: {backend}")
    if backend == "marian":
        if (source_lang, target_lang) != ("en", "de"):
            raise ValueError("Marian supports only en to de; choose a compatible language pair")
    elif source_lang not in ("en", "de") or target_lang not in ("en", "de"):
        raise ValueError("Qwen supports only en and de")
