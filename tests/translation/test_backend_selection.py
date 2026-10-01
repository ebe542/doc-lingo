"""Application language validation stays independent of optional model packages."""

import pytest

from doc_lingo.translation.selection import validate_language_pair


@pytest.mark.parametrize(
    "backend,source,target",
    [
        ("marian", "en", "de"),
        ("qwen", "en", "de"),
        ("qwen", "de", "en"),
        ("qwen", "en", "en"),
        ("qwen", "de", "de"),
    ],
)
def test_supported_languages(backend, source, target):
    validate_language_pair(backend, source, target)


@pytest.mark.parametrize(
    "backend,source,target",
    [
        ("marian", "de", "en"),
        ("marian", "en", "en"),
        ("qwen", "fr", "de"),
        ("qwen", "en", "fr"),
        ("unknown", "en", "de"),
    ],
)
def test_unsupported_languages(backend, source, target):
    with pytest.raises(ValueError):
        validate_language_pair(backend, source, target)
