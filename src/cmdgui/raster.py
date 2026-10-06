"""Drawing on a grid of pixels: lines, shapes, curves. The Graphics widget uses
this, and so can any widget that wants to draw in pixels.

A pixel is a color (anything style() accepts) or None for nothing there.
Coordinates can be floats; pixel (x, y) is centred on those whole numbers, so
circle(10, 10, 5) covers pixels 5 to 15. Anything off the edge is clipped."""
from __future__ import annotations

import math
from typing import Iterable, Optional, Sequence
from .shorts import Color, _color_code

Point = Sequence[float]

_checked = set() # colors already known to be valid


def check_color(color) -> Optional[Color]:
    """The color, ready to store in a pixel (lists become tuples). Raises
    ValueError for an unknown color now, rather than when it's drawn."""
    if color is None: return None
    if isinstance(color, list): color = tuple(color)
    try:
        if color in _checked: return color
    except TypeError:
        raise ValueError(f"unknown color {color!r}") from None
    _color_code(color, 30) # raises ValueError if it isn't a color
    _checked.add(color)
    return color


def _round(v):
    """Round halves up, so shapes don't shift with Python's round-half-to-even."""
    return math.floor(v + 0.5)


def _clip(x0, y0, x1, y1, xmin, ymin, xmax, ymax):
    """Liang-Barsky: the part of a line inside the box, or None."""
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - xmin), (dx, xmax - x0), (-dy, y0 - ymin), (dy, ymax - y0)):
        if p == 0:
            if q < 0: return None # parallel to this edge, and outside it
            continue
        t = q / p
        if p < 0: t0 = max(t0, t)
        else: t1 = min(t1, t)
        if t0 > t1: return None
    return x0 + t0 * dx, y0 + t0 * dy, x0 + t1 * dx, y0 + t1 * dy


def _bezier_point(points, t):
    """De Casteljau: the point at t (0 to 1) along a curve with these control points."""
    while len(points) > 1:
        points = [(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t) for a, b in zip(points, points[1:])]
    return points[0]


class Raster:
    """Pixel drawing methods. Subclasses call _init_pixels(), and can override
    _begin() (called before each drawing method) and _changed() (after)."""

    def _init_pixels(self, width=0, height=0):
        self._pw, self._ph = width, height
        self._rows: list[list] = [[None] * width for _ in range(height)]

    @property
    def pixel_width(self) -> int:
        return self._pw

    @property
    def pixel_height(self) -> int:
        return self._ph

    def _resize_pixels(self, width, height):
        """Change the size, keeping what fits from the top-left corner."""
        rows = [[None] * width for _ in range(height)]
        keep = min(width, self._pw)
        for new, old in zip(rows, self._rows):
            new[:keep] = old[:keep]
        self._pw, self._ph, self._rows = width, height, rows

    def _begin(self): pass
    def _changed(self): pass

    # --- Low level, no checks or hooks ---

    def _put(self, x, y, color):
        if 0 <= x < self._pw and 0 <= y < self._ph:
            self._rows[y][x] = color

    def _span(self, y, x0, x1, color):
        """A horizontal run of pixels from x0 to x1, inclusive."""
        if not 0 <= y < self._ph: return
        x0, x1 = max(0, min(x0, x1)), min(self._pw - 1, max(x0, x1))
        if x0 <= x1:
            self._rows[y][x0:x1 + 1] = [color] * (x1 - x0 + 1)

    def _line(self, x0, y0, x1, y1, color):
        # Clip first (with a pixel to spare for rounding), so a line to (1e9, 0) doesn't take forever
        clipped = _clip(x0, y0, x1, y1, -1, -1, self._pw, self._ph)
        if clipped is None: return
        x0, y0, x1, y1 = (_round(v) for v in clipped)
        # Bresenham
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        while True:
            self._put(x0, y0, color)
            if x0 == x1 and y0 == y1: return
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def _polyline(self, points, color, closed=False):
        points = [(float(x), float(y)) for x, y in points]
        if not points: return
        if len(points) == 1:
            self._put(_round(points[0][0]), _round(points[0][1]), color)
            return
        if closed: points.append(points[0])
        for (xa, ya), (xb, yb) in zip(points, points[1:]):
            self._line(xa, ya, xb, yb, color)

    def _ellipse(self, cx, cy, rx, ry, color, fill):
        rx, ry = abs(rx), abs(ry)
        if rx < 0.5 or ry < 0.5: # too thin to have an inside: a line (or a dot)
            self._line(cx - rx, cy - ry, cx + rx, cy + ry, color)
            return
        if fill:
            for y in range(max(0, math.ceil(cy - ry)), min(self._ph - 1, math.floor(cy + ry)) + 1):
                half = rx * math.sqrt(max(0.0, 1 - ((y - cy) / ry) ** 2))
                self._span(y, _round(cx - half), _round(cx + half), color)
        # The outline: scanning rows and then columns leaves no gaps where it's steep or flat
        for y in range(max(0, math.ceil(cy - ry)), min(self._ph - 1, math.floor(cy + ry)) + 1):
            half = rx * math.sqrt(max(0.0, 1 - ((y - cy) / ry) ** 2))
            self._put(_round(cx - half), y, color)
            self._put(_round(cx + half), y, color)
        for x in range(max(0, math.ceil(cx - rx)), min(self._pw - 1, math.floor(cx + rx)) + 1):
            half = ry * math.sqrt(max(0.0, 1 - ((x - cx) / rx) ** 2))
            self._put(x, _round(cy - half), color)
            self._put(x, _round(cy + half), color)

    # --- Drawing ---

    def get(self, x: float, y: float) -> Optional[Color]:
        """The color of a pixel, or None if it's empty or off the edge."""
        self._begin()
        x, y = _round(x), _round(y)
        return self._rows[y][x] if 0 <= x < self._pw and 0 <= y < self._ph else None

    def pixel(self, x: float, y: float, color: Optional[Color]) -> None:
        """Set one pixel. None clears it."""
        color = check_color(color)
        self._begin()
        self._put(_round(x), _round(y), color)
        self._changed()

    def clear(self, color: Optional[Color] = None) -> None:
        """Set every pixel to color, or clear them all."""
        color = check_color(color)
        self._begin()
        self._rows = [[color] * self._pw for _ in range(self._ph)]
        self._changed()

    def line(self, x0: float, y0: float, x1: float, y1: float, color: Optional[Color]) -> None:
        color = check_color(color)
        self._begin()
        self._line(x0, y0, x1, y1, color)
        self._changed()

    def polyline(self, points: Iterable[Point], color: Optional[Color], closed: bool = False) -> None:
        """Lines joining the points in order (and back to the first, if closed)."""
        color = check_color(color)
        self._begin()
        self._polyline(points, color, closed)
        self._changed()

    def rect(self, x: float, y: float, width: float, height: float, color: Optional[Color],
             fill: bool = False) -> None:
        """A rectangle with its top-left pixel at (x, y), width x height pixels."""
        color = check_color(color)
        self._begin()
        if width < 0: x, width = x + width, -width # a negative size goes left / up from (x, y)
        if height < 0: y, height = y + height, -height
        x0, x1 = _round(x), _round(x + width) - 1
        y0, y1 = _round(y), _round(y + height) - 1
        if x1 < x0 or y1 < y0: return # less than a pixel
        if fill:
            for row in range(max(0, y0), min(self._ph - 1, y1) + 1):
                self._span(row, x0, x1, color)
        else:
            self._span(y0, x0, x1, color)
            self._span(y1, x0, x1, color)
            for row in range(max(0, y0), min(self._ph - 1, y1) + 1):
                self._put(x0, row, color)
                self._put(x1, row, color)
        self._changed()

    def circle(self, cx: float, cy: float, radius: float, color: Optional[Color], fill: bool = False) -> None:
        color = check_color(color)
        self._begin()
        self._ellipse(cx, cy, radius, radius, color, fill)
        self._changed()

    def ellipse(self, cx: float, cy: float, rx: float, ry: float, color: Optional[Color],
                fill: bool = False) -> None:
        """An ellipse centred on (cx, cy), rx across and ry down from the centre."""
        color = check_color(color)
        self._begin()
        self._ellipse(cx, cy, rx, ry, color, fill)
        self._changed()

    def arc(self, cx: float, cy: float, radius: float, start: float, end: float,
            color: Optional[Color]) -> None:
        """Part of a circle, from start to end in degrees. 0 is to the right of the
        centre, and angles go clockwise (down is 90)."""
        color = check_color(color)
        self._begin()
        sweep = end - start
        steps = max(4, min(2000, math.ceil(abs(math.radians(sweep)) * abs(radius))))
        points = []
        for i in range(steps + 1):
            angle = math.radians(start + sweep * i / steps)
            points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        self._polyline(points, color)
        self._changed()

    def bezier(self, points: Sequence[Point], color: Optional[Color]) -> None:
        """A curve from the first point to the last, pulled towards the ones in
        between: 3 points for a quadratic curve, 4 for a cubic, or more."""
        color = check_color(color)
        self._begin()
        points = [(float(x), float(y)) for x, y in points]
        if len(points) < 2:
            self._polyline(points, color)
        else:
            # Roughly one segment per pixel along the control points
            length = sum(math.dist(a, b) for a, b in zip(points, points[1:]))
            steps = max(1, min(2000, math.ceil(length)))
            self._polyline([_bezier_point(points, i / steps) for i in range(steps + 1)], color)
        self._changed()

    def polygon(self, points: Sequence[Point], color: Optional[Color], fill: bool = False) -> None:
        """A closed shape through the points. Filled with the even-odd rule, so a
        shape that crosses itself (like a star drawn in one go) has holes."""
        color = check_color(color)
        self._begin()
        points = [(float(x), float(y)) for x, y in points]
        if fill and len(points) >= 3:
            edges = list(zip(points, points[1:] + points[:1]))
            top = max(0, math.ceil(min(y for _, y in points)))
            bottom = min(self._ph - 1, math.floor(max(y for _, y in points)))
            for y in range(top, bottom + 1):
                xs = sorted(xa + (y - ya) * (xb - xa) / (yb - ya)
                            for (xa, ya), (xb, yb) in edges if (ya <= y < yb) or (yb <= y < ya))
                for xa, xb in zip(xs[::2], xs[1::2]):
                    self._span(y, _round(xa), _round(xb), color)
        self._polyline(points, color, closed=True) # the edges, so a fill matches its outline
        self._changed()

    def image(self, pixels: Sequence[Sequence[Optional[Color]]], x: float = 0, y: float = 0) -> None:
        """Copy rows of colors in with their top-left at (x, y). None is see-through."""
        self._begin()
        x, y = _round(x), _round(y)
        for row, values in enumerate(pixels):
            for col, color in enumerate(values):
                if color is not None:
                    self._put(x + col, y + row, check_color(color))
        self._changed()
