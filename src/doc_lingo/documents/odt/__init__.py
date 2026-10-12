"""Read-only ODT package inspection; document translation is not yet available."""

from doc_lingo.documents.odt.package import OdtPackageError, OdtPackageInfo, inspect_package

__all__ = ["OdtPackageError", "OdtPackageInfo", "inspect_package"]
