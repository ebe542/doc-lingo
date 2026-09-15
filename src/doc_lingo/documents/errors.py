"""Document validation errors."""


class SegmentMismatchError(ValueError):
    """Translations do not match the original document's ordered segment IDs."""
