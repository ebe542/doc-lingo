"""Conservative classification of text styles without visible formatting."""

from xml.etree import ElementTree as ET

from doc_lingo.documents.odt.package import OdtPackageInfo

STYLE = "urn:oasis:names:tc:opendocument:xmlns:style:1.0"
FO = "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"


def language_only_styles(package: OdtPackageInfo) -> frozenset[str]:
    """Use validated package XML; unknown or inherited properties stay visual.

    A name must have exactly one definition across both XML parts. Do not infer
    absence of visual effects through parent styles or extension attributes.
    """
    definitions = {}
    for xml in (package.content_xml, package.styles_xml):
        if xml is None:
            continue
        for style in ET.fromstring(xml).iter(f"{{{STYLE}}}style"):
            name = style.get(f"{{{STYLE}}}name")
            definitions.setdefault(name, []).append(style)
    result = set()
    for name, entries in definitions.items():
        if not name or len(entries) != 1:
            continue
        style = entries[0]
        if (
            style.get(f"{{{STYLE}}}family") != "text"
            or set(style.attrib) != {f"{{{STYLE}}}name", f"{{{STYLE}}}family"}
            or len(style) != 1
        ):
            continue
        properties = style[0]
        if (
            properties.tag == f"{{{STYLE}}}text-properties"
            and not len(properties)
            and f"{{{FO}}}language" in properties.attrib
            and set(properties.attrib)
            <= {f"{{{FO}}}language", f"{{{FO}}}country", f"{{{STYLE}}}script-type"}
        ):
            result.add(name)
    return frozenset(result)
