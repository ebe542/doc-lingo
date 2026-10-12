"""ODT inspection and a limited plain-text reader/writer; no CLI integration."""

from doc_lingo.documents.odt.package import OdtPackageError, OdtPackageInfo, inspect_package
from doc_lingo.documents.odt.reader import OdtReader
from doc_lingo.documents.odt.writer import OdtWriter

__all__ = ["OdtPackageError", "OdtPackageInfo", "OdtReader", "OdtWriter", "inspect_package"]
