"""Build portable graphic assets from extracted objects for the first SLA trial."""

import base64
import xml.etree.ElementTree as ET

SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)


def _tag(name):
    return f"{{{SVG}}}{name}"


def _path(items):
    commands, last = [], None
    for item in items:
        kind = item[0]
        if kind in {"l", "c"}:
            if last != item[1]:
                commands.append(f"M {item[1][0]} {item[1][1]}")
            points = item[2:]
            commands.append(
                ("L " if kind == "l" else "C ")
                + " ".join(str(value) for point in points for value in point)
            )
            last = points[-1]
        elif kind in {"re", "qu"}:
            if kind == "re":
                x0, y0, x1, y1 = item[1]
                points = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
                if item[2] < 0:
                    points.reverse()
            else:
                a, b, c, d = item[1]
                points = [a, b, d, c]
            commands.append("M " + " L ".join(f"{x} {y}" for x, y in points) + " Z")
            last = None
        else:
            raise ValueError(f"Unsupported vector command: {kind}")
    return " ".join(commands)


def _color(rgb):
    return "none" if rgb is None else "#" + "".join(f"{round(c * 255):02x}" for c in rgb)


def vector_svg(path, clips, box):
    x0, y0, x1, y1 = box
    root = ET.Element(
        _tag("svg"),
        {
            "width": f"{x1 - x0}pt",
            "height": f"{y1 - y0}pt",
            "viewBox": f"{x0} {y0} {x1 - x0} {y1 - y0}",
        },
    )
    defs = ET.SubElement(root, _tag("defs"))
    parent = root
    for index, clip in enumerate(clips):
        node = ET.SubElement(
            defs, _tag("clipPath"), {"id": f"clip{index}", "clipPathUnits": "userSpaceOnUse"}
        )
        ET.SubElement(
            node,
            _tag("path"),
            {
                "d": _path(clip["items"]),
                "clip-rule": "evenodd" if clip.get("even_odd") else "nonzero",
            },
        )
        parent = ET.SubElement(parent, _tag("g"), {"clip-path": f"url(#clip{index})"})
    attributes = {
        "d": _path(path["items"]) + (" Z" if path.get("closePath") else ""),
        "fill": _color(path.get("fill")),
        "stroke": _color(path.get("color")),
        "stroke-width": str(path.get("width", 0)),
        "fill-opacity": str(path.get("fill_opacity", 1)),
        "stroke-opacity": str(path.get("stroke_opacity", 1)),
        "fill-rule": "evenodd" if path.get("even_odd") else "nonzero",
        "stroke-linecap": {0: "butt", 1: "round", 2: "square"}.get(
            max(path.get("lineCap", [0])), "butt"
        ),
        "stroke-linejoin": {0: "miter", 1: "round", 2: "bevel"}.get(
            path.get("lineJoin", 0), "miter"
        ),
    }
    ET.SubElement(parent, _tag("path"), attributes)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def image_png(layout, obj):
    """Flatten image transform/mask into a standalone PNG inside its observed bbox."""
    import pymupdf

    def asset(relative):
        path = (layout / relative).resolve()
        if not path.is_relative_to(layout.resolve()):
            raise ValueError("Image asset escapes layout directory")
        return path.read_bytes()

    pixmap = pymupdf.Pixmap(asset(obj["file"]))
    if pixmap.colorspace and pixmap.colorspace.n != 3:
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pixmap)
    if obj.get("mask_file"):
        pixmap = pymupdf.Pixmap(pixmap, pymupdf.Pixmap(asset(obj["mask_file"])))
    encoded = base64.b64encode(pixmap.tobytes("png")).decode("ascii")
    x0, y0, x1, y1 = obj["source"]["bbox"]
    matrix = " ".join(str(value) for value in obj["source"]["transform"])
    svg = (
        f'<svg xmlns="{SVG}" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{x1 - x0}pt" height="{y1 - y0}pt" viewBox="{x0} {y0} {x1 - x0} {y1 - y0}">'
        f'<image width="1" height="1" preserveAspectRatio="none" transform="matrix({matrix})" '
        f'xlink:href="data:image/png;base64,{encoded}"/></svg>'
    )
    with pymupdf.open(stream=svg.encode(), filetype="svg") as document:
        return document[0].get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=True).tobytes("png")
