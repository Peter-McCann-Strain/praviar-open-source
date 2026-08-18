"""Raster Praviar mark helpers for Office export formats."""

from __future__ import annotations

import re
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Literal, NamedTuple

from defusedxml.ElementTree import fromstring

if TYPE_CHECKING:
    from collections.abc import Iterable

MarkVariant = Literal["on_light", "on_dark"]

Point = tuple[float, float]

_SOFT_MINT = "#D7ECE5"

_BRAND_MARK_SVG = Path(__file__).resolve().parent / "templates" / "brand" / "praviar-mark.svg"
_PATH_TOKEN_RE = re.compile(r"[MmHhVvLlCcZz]|-?(?:\d+\.\d+|\d+|\.\d+)(?:[eE][-+]?\d+)?")


class SvgMarkPath(NamedTuple):
    d: str
    fill: str


@lru_cache(maxsize=1)
def _load_praviar_mark_svg_paths() -> tuple[SvgMarkPath, ...]:
    root = fromstring(_BRAND_MARK_SVG.read_text(encoding="utf-8"))
    paths: list[SvgMarkPath] = []

    for element in root.iter():
        if not element.tag.endswith("path"):
            continue
        path_data = element.attrib.get("d")
        fill = element.attrib.get("fill")
        if not path_data or not fill:
            raise RuntimeError(f"Praviar mark path in {_BRAND_MARK_SVG} is missing d/fill")
        paths.append(SvgMarkPath(path_data, fill))

    if len(paths) != 6:
        raise RuntimeError(
            f"Expected 6 Praviar mark paths in {_BRAND_MARK_SVG}, found {len(paths)}"
        )

    return tuple(paths)


def _cubic_points(
    start: Point,
    control_1: Point,
    control_2: Point,
    end: Point,
    *,
    steps: int = 18,
) -> list[Point]:
    points: list[Point] = []
    for step in range(1, steps + 1):
        t = step / steps
        inverse = 1 - t
        x = (
            inverse**3 * start[0]
            + 3 * inverse**2 * t * control_1[0]
            + 3 * inverse * t**2 * control_2[0]
            + t**3 * end[0]
        )
        y = (
            inverse**3 * start[1]
            + 3 * inverse**2 * t * control_1[1]
            + 3 * inverse * t**2 * control_2[1]
            + t**3 * end[1]
        )
        points.append((x, y))
    return points


def _read_path_number(tokens: list[str], index: int, path_data: str) -> tuple[float, int]:
    if index >= len(tokens) or tokens[index].isalpha():
        raise ValueError(f"Expected path number while parsing {path_data!r}")
    return float(tokens[index]), index + 1


def _path_polygon(path_data: str) -> list[Point]:
    tokens = _PATH_TOKEN_RE.findall(path_data)
    points: list[Point] = []
    command: str | None = None
    current: Point | None = None
    start: Point | None = None
    index = 0

    while index < len(tokens):
        token = tokens[index]
        if token.isalpha():
            command = token
            index += 1

        if command is None:
            raise ValueError(f"Expected path command while parsing {path_data!r}")
        if command.islower():
            raise ValueError(f"Relative SVG path commands are not supported in {path_data!r}")

        if command == "M":
            x, index = _read_path_number(tokens, index, path_data)
            y, index = _read_path_number(tokens, index, path_data)
            current = (x, y)
            start = current
            points.append(current)
            command = "L"
        elif command == "L":
            x, index = _read_path_number(tokens, index, path_data)
            y, index = _read_path_number(tokens, index, path_data)
            current = (x, y)
            points.append(current)
        elif command == "H":
            if current is None:
                raise ValueError(f"Horizontal line requires a current point in {path_data!r}")
            x, index = _read_path_number(tokens, index, path_data)
            current = (x, current[1])
            points.append(current)
        elif command == "V":
            if current is None:
                raise ValueError(f"Vertical line requires a current point in {path_data!r}")
            y, index = _read_path_number(tokens, index, path_data)
            current = (current[0], y)
            points.append(current)
        elif command == "C":
            if current is None:
                raise ValueError(f"Curve command requires a current point in {path_data!r}")
            control_1_x, index = _read_path_number(tokens, index, path_data)
            control_1_y, index = _read_path_number(tokens, index, path_data)
            control_2_x, index = _read_path_number(tokens, index, path_data)
            control_2_y, index = _read_path_number(tokens, index, path_data)
            end_x, index = _read_path_number(tokens, index, path_data)
            end_y, index = _read_path_number(tokens, index, path_data)
            control_1 = (control_1_x, control_1_y)
            control_2 = (control_2_x, control_2_y)
            end = (end_x, end_y)
            points.extend(_cubic_points(current, control_1, control_2, end))
            current = end
        elif command == "Z":
            current = start
            command = None
        else:
            raise ValueError(f"Unsupported SVG path command {command!r} in {path_data!r}")

    return points


def _scale_polygon(points: Iterable[Point], scale: float) -> list[tuple[int, int]]:
    return [(round(x * scale), round(y * scale)) for x, y in points]


def render_praviar_mark_png_stream(
    *,
    variant: MarkVariant = "on_light",
    size_px: int = 512,
) -> BytesIO:
    """Render the Praviar mark to an in-memory PNG for DOCX/PPTX.

    The PDF and web surfaces use SVG directly. Office formats need a raster
    image, so this draws the same evidence mark with supersampling to keep the
    small cover lockups crisp.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:  # pragma: no cover - python-pptx depends on Pillow.
        raise RuntimeError("Pillow is required to render the Praviar mark") from exc

    scale_factor = 4
    canvas_size = size_px * scale_factor
    scale = canvas_size / 230
    image = Image.new("RGBA", (canvas_size, canvas_size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    svg_paths = _load_praviar_mark_svg_paths()

    for index, path in enumerate(svg_paths):
        polygon = _scale_polygon(_path_polygon(path.d), scale)
        draw.polygon(polygon, fill=path.fill)
        if index == 0 and variant == "on_light":
            outline_width = max(1, round(4 * scale))
            draw.line([*polygon, polygon[0]], fill=_SOFT_MINT, width=outline_width)

    resampling = getattr(Image, "Resampling", Image).LANCZOS
    image = image.resize((size_px, size_px), resampling)
    stream = BytesIO()
    image.save(stream, format="PNG")
    stream.seek(0)
    return stream
