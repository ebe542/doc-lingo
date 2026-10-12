"""Small generated ODT inputs; no editor, model, or private document required."""

from base64 import b64decode
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest

OFFICE = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
MANIFEST = "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
MIME = b"application/vnd.oasis.opendocument.text"
CONTENT = f'''<office:document-content xmlns:office="{OFFICE}"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
 xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
 xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
 xmlns:xlink="http://www.w3.org/1999/xlink" office:version="1.3">
 <office:body><office:text>
 <text:h text:outline-level="1">Example</text:h>
 <text:p>One <text:span>formatted</text:span> paragraph<text:s text:c="2"/>
 with a<text:tab/>tab<text:line-break/>and break.</text:p>
 <text:list><text:list-item><text:p>First</text:p>
 <text:list><text:list-item><text:p>Nested</text:p></text:list-item></text:list>
 </text:list-item></text:list>
 <table:table><table:table-column/><table:table-row><table:table-cell>
 <text:p>Cell one</text:p><text:p>Cell two</text:p>
 </table:table-cell></table:table-row></table:table>
 <text:p><text:bookmark text:name="example"/><text:page-number>1</text:page-number>
 <draw:frame><draw:image xlink:href="Pictures/pixel.png" xlink:type="simple"/>
 </draw:frame></text:p>
 </office:text></office:body></office:document-content>'''.encode()
STYLES = f'<office:document-styles xmlns:office="{OFFICE}" office:version="1.3"/>'.encode()
MANIFEST_XML = f'''<manifest:manifest xmlns:manifest="{MANIFEST}" manifest:version="1.3">
 <manifest:file-entry manifest:full-path="/" manifest:media-type="{MIME.decode()}"/>
 <manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
 <manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/>
 <manifest:file-entry manifest:full-path="Pictures/pixel.png" manifest:media-type="image/png"/>
 </manifest:manifest>'''.encode()
PIXEL = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j4ZkAAAAASUVORK5CYII="
)


@pytest.fixture
def odt_factory(tmp_path):
    def create(*, updates=None, omit=(), extra=(), mime_compression=ZIP_STORED):
        members = {
            "mimetype": MIME,
            "content.xml": CONTENT,
            "styles.xml": STYLES,
            "Pictures/pixel.png": PIXEL,
            "META-INF/manifest.xml": MANIFEST_XML,
        }
        members.update(updates or {})
        path = tmp_path / "sample.odt"
        with ZipFile(path, "w") as archive:
            for name, data in [*members.items(), *extra]:
                if name not in omit:
                    archive.writestr(
                        name,
                        data,
                        compress_type=(mime_compression if name == "mimetype" else ZIP_DEFLATED),
                    )
        return path

    return create
