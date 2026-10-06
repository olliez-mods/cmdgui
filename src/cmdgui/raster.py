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


# A 3x5 pixel font: each glyph is 5 rows of 3 pixels, 1 for ink. Capitals only,
# lowercase is drawn in capitals. Characters it doesn't have are drawn as "?".
FONT_WIDTH, FONT_HEIGHT = 3, 5
FONT = {
    " ": "000 000 000 000 000", "!": "010 010 010 000 010", '"': "101 101 000 000 000",
    "#": "101 111 101 111 101", "$": "011 110 010 011 110", "%": "101 001 010 100 101",
    "&": "010 101 010 101 011", "'": "010 010 000 000 000", "(": "001 010 010 010 001",
    ")": "100 010 010 010 100", "*": "000 101 010 101 000", "+": "000 010 111 010 000",
    ",": "000 000 000 010 100", "-": "000 000 111 000 000", ".": "000 000 000 000 010",
    "/": "001 001 010 100 100", "0": "111 101 101 101 111", "1": "010 110 010 010 111",
    "2": "111 001 111 100 111", "3": "111 001 011 001 111", "4": "101 101 111 001 001",
    "5": "111 100 111 001 111", "6": "111 100 111 101 111", "7": "111 001 001 010 010",
    "8": "111 101 111 101 111", "9": "111 101 111 001 111", ":": "000 010 000 010 000",
    ";": "000 010 000 010 100", "<": "001 010 100 010 001", "=": "000 111 000 111 000",
    ">": "100 010 001 010 100", "?": "111 001 011 000 010", "@": "010 101 111 100 011",
    "A": "010 101 111 101 101", "B": "110 101 110 101 110", "C": "011 100 100 100 011",
    "D": "110 101 101 101 110", "E": "111 100 110 100 111", "F": "111 100 110 100 100",
    "G": "011 100 101 101 011", "H": "101 101 111 101 101", "I": "111 010 010 010 111",
    "J": "001 001 001 101 010", "K": "101 101 110 101 101", "L": "100 100 100 100 111",
    "M": "101 111 111 101 101", "N": "110 101 101 101 101", "O": "010 101 101 101 010",
    "P": "110 101 110 100 100", "Q": "010 101 101 110 011", "R": "110 101 110 101 101",
    "S": "011 100 010 001 110", "T": "111 010 010 010 010", "U": "101 101 101 101 111",
    "V": "101 101 101 101 010", "W": "101 101 111 111 101", "X": "101 101 010 101 101",
    "Y": "101 101 010 010 010", "Z": "111 001 010 100 111", "[": "110 100 100 100 110",
    "\\": "100 100 010 001 001", "]": "011 001 001 001 011", "^": "010 101 000 000 000",
    "_": "000 000 000 000 111", "`": "100 010 000 000 000", "{": "011 010 110 010 011",
    "|": "010 010 010 010 010", "}": "110 010 011 010 110", "~": "000 011 110 000 000",
}
# Each glyph as the (x, y) of its ink
_GLYPHS = {char: [(x, y) for y, row in enumerate(rows.split()) for x, bit in enumerate(row) if bit == "1"]
           for char, rows in FONT.items()}


def text_size(text: str, scale: int = 1, aspect: float = 1.0) -> tuple[int, int]:
    """How many pixels wide and tall text() draws text, for pixels aspect times
    taller than wide."""
    lines = text.split("\n")
    width = max(len(line) for line in lines) * (FONT_WIDTH + 1) - 1
    height = len(lines) * (FONT_HEIGHT + 1) - 1
    return _round(max(0, width) * scale * aspect), height * scale


class Raster:
    """Pixel drawing methods. Subclasses call _init_pixels(), and can override
    _begin() (called before each drawing method) and _changed() (after)."""
    # Keep circles round and text in shape where pixels aren't square: heights of
    # round shapes are divided by pixel_aspect, and text is widened by it
    fix_aspect = True

    def _init_pixels(self, width=0, height=0):
        self._pw, self._ph = width, height
        self._rows: list[list] = [[None] * width for _ in range(height)]

    @property
    def pixel_width(self) -> int:
        self._begin() # up to date with a widget's size
        return self._pw

    @property
    def pixel_height(self) -> int:
        self._begin()
        return self._ph

    @property
    def pixel_aspect(self) -> float:
        """How many times taller than wide a pixel is on screen."""
        return 1.0

    def _aspect(self):
        """How much to squash round things vertically: pixel_aspect, or 1 with fix_aspect off."""
        return self.pixel_aspect if self.fix_aspect else 1.0

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

    # Thick lines. These count a pixel as covered when its centre is inside the shape,
    # so a line 2 thick is 2 pixels thick. Thickness is in pixels across; down, it's
    # divided by the aspect, so lines look as thick one way as the other.

    def _fill_polygon(self, points, color):
        """Fill the pixels whose centres are inside the polygon (even-odd)."""
        edges = list(zip(points, points[1:] + points[:1]))
        top = max(0, math.ceil(min(y for _, y in points)))
        bottom = min(self._ph, math.ceil(max(y for _, y in points)))
        for y in range(top, bottom):
            xs = sorted(xa + (y - ya) * (xb - xa) / (yb - ya)
                        for (xa, ya), (xb, yb) in edges if (ya <= y < yb) or (yb <= y < ya))
            for xa, xb in zip(xs[::2], xs[1::2]):
                if math.ceil(xb) > math.ceil(xa):
                    self._span(y, math.ceil(xa), math.ceil(xb) - 1, color)

    def _disc(self, cx, cy, rx, ry, color):
        """Fill the pixels whose centres are inside the ellipse."""
        if ry <= 0: return
        for y in range(max(0, math.ceil(cy - ry)), min(self._ph, math.ceil(cy + ry))):
            half = rx * math.sqrt(max(0.0, 1 - ((y - cy) / ry) ** 2))
            if math.ceil(cx + half) > math.ceil(cx - half):
                self._span(y, math.ceil(cx - half), math.ceil(cx + half) - 1, color)

    def _thick_polyline(self, points, color, thickness, closed=False):
        """Lines with round ends and joins."""
        if thickness <= 1:
            self._polyline(points, color, closed)
            return
        points = [(float(x), float(y)) for x, y in points]
        if not points: return
        if closed and len(points) > 2: points.append(points[0])
        a, r = self._aspect(), thickness / 2
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            # Work out the sides where pixels are square (y times the aspect), then back
            dx, dy = x1 - x0, (y1 - y0) * a
            length = math.hypot(dx, dy)
            if length == 0: continue
            nx, ny = -dy / length * r, dx / length * r / a
            self._fill_polygon([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)], color)
        for x, y in points:
            self._disc(x, y, r, r / a, color)

    def _ring(self, cx, cy, rx, ry, color, thickness):
        """An ellipse's outline, thickness pixels across, centred on the edge."""
        a, r = self._aspect(), thickness / 2
        orx, ory, irx, iry = rx + r, ry + r / a, rx - r, ry - r / a
        if irx <= 0 or iry <= 0:
            self._disc(cx, cy, orx, ory, color)
            return
        for y in range(max(0, math.ceil(cy - ory)), min(self._ph, math.ceil(cy + ory))):
            outer = orx * math.sqrt(max(0.0, 1 - ((y - cy) / ory) ** 2))
            left, right = math.ceil(cx - outer), math.ceil(cx + outer) - 1
            if abs(y - cy) >= iry: # above or below the hole
                if right >= left: self._span(y, left, right, color)
                continue
            inner = irx * math.sqrt(max(0.0, 1 - ((y - cy) / iry) ** 2))
            if math.ceil(cx - inner) > left: self._span(y, left, math.ceil(cx - inner) - 1, color)
            if right >= math.ceil(cx + inner): self._span(y, math.ceil(cx + inner), right, color)

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

    def line(self, x0: float, y0: float, x1: float, y1: float, color: Optional[Color],
             thickness: float = 1) -> None:
        """A line thickness pixels wide, with round ends when it's thicker than 1."""
        color = check_color(color)
        self._begin()
        if thickness > 1: self._thick_polyline([(x0, y0), (x1, y1)], color, thickness)
        else: self._line(x0, y0, x1, y1, color)
        self._changed()

    def polyline(self, points: Iterable[Point], color: Optional[Color], closed: bool = False,
                 thickness: float = 1) -> None:
        """Lines joining the points in order (and back to the first, if closed)."""
        color = check_color(color)
        self._begin()
        self._thick_polyline(points, color, thickness, closed)
        self._changed()

    def rect(self, x: float, y: float, width: float, height: float, color: Optional[Color],
             fill: bool = False, thickness: float = 1) -> None:
        """A rectangle with its top-left pixel at (x, y), width x height pixels. A thick
        outline goes inwards, so the rectangle stays the same size."""
        color = check_color(color)
        self._begin()
        if width < 0: x, width = x + width, -width # a negative size goes left / up from (x, y)
        if height < 0: y, height = y + height, -height
        x0, x1 = _round(x), _round(x + width) - 1
        y0, y1 = _round(y), _round(y + height) - 1
        if x1 < x0 or y1 < y0: return # less than a pixel
        across = max(1, _round(thickness))                   # the sides' width
        down = max(1, _round(thickness / self._aspect()))    # the top and bottom's height
        for row in range(max(0, y0), min(self._ph - 1, y1) + 1):
            if fill or row < y0 + down or row > y1 - down:
                self._span(row, x0, x1, color)
            else:
                self._span(row, x0, min(x1, x0 + across - 1), color)
                self._span(row, max(x0, x1 - across + 1), x1, color)
        self._changed()

    def circle(self, cx: float, cy: float, radius: float, color: Optional[Color], fill: bool = False,
               thickness: float = 1) -> None:
        """A circle radius pixels across from the centre to the edge. With fix_aspect
        (the default), it's round in every mode."""
        self.ellipse(cx, cy, radius, radius, color, fill, thickness)

    def ellipse(self, cx: float, cy: float, rx: float, ry: float, color: Optional[Color],
                fill: bool = False, thickness: float = 1) -> None:
        """An ellipse centred on (cx, cy), rx across and ry down from the centre. With
        fix_aspect, ry is measured like rx (in pixels across), so the shape is right
        on screen; turn it off to have ry in pixels down."""
        color = check_color(color)
        self._begin()
        rx, ry = abs(rx), abs(ry) / self._aspect()
        if thickness > 1:
            if fill: self._disc(cx, cy, rx, ry, color)
            self._ring(cx, cy, rx, ry, color, thickness)
        else:
            self._ellipse(cx, cy, rx, ry, color, fill)
        self._changed()

    def arc(self, cx: float, cy: float, radius: float, start: float, end: float,
            color: Optional[Color], thickness: float = 1) -> None:
        """Part of a circle, from start to end in degrees. 0 is to the right of the
        centre, and angles go clockwise (down is 90)."""
        color = check_color(color)
        self._begin()
        sweep, down = end - start, radius / self._aspect()
        steps = max(4, min(2000, math.ceil(abs(math.radians(sweep)) * abs(radius))))
        points = []
        for i in range(steps + 1):
            angle = math.radians(start + sweep * i / steps)
            points.append((cx + radius * math.cos(angle), cy + down * math.sin(angle)))
        self._thick_polyline(points, color, thickness)
        self._changed()

    def bezier(self, points: Sequence[Point], color: Optional[Color], thickness: float = 1) -> None:
        """A curve from the first point to the last, pulled towards the ones in
        between: 3 points for a quadratic curve, 4 for a cubic, or more."""
        color = check_color(color)
        self._begin()
        points = [(float(x), float(y)) for x, y in points]
        if len(points) >= 2:
            # Roughly one segment per pixel along the control points, fewer for thick
            # lines, whose round joins hide the corners
            length = sum(math.dist(a, b) for a, b in zip(points, points[1:]))
            steps = max(1, min(2000, math.ceil(length / max(1, thickness / 2))))
            points = [_bezier_point(points, i / steps) for i in range(steps + 1)]
        self._thick_polyline(points, color, thickness)
        self._changed()

    def polygon(self, points: Sequence[Point], color: Optional[Color], fill: bool = False,
                thickness: float = 1) -> None:
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
        self._thick_polyline(points, color, thickness, closed=True) # the edges, so a fill matches its outline
        self._changed()

    def text(self, x: float, y: float, text: str, color: Optional[Color], scale: int = 1,
             fix_aspect: Optional[bool] = None) -> None:
        """Write text in a 3x5 pixel font (capitals only), its top-left at (x, y).
        scale makes it bigger: 2 draws each font pixel as 2x2. text_size() measures it.
        fix_aspect: where pixels are taller than wide (quad and sextant), widen the
        letters to match, so they keep their shape. None uses the fix_aspect setting."""
        color = check_color(color)
        self._begin()
        scale = max(1, int(scale))
        if fix_aspect is None: fix_aspect = self.fix_aspect
        across = scale * (self.pixel_aspect if fix_aspect else 1) # pixels per font pixel, across
        x0, y = _round(x), _round(y)
        for line in text.split("\n"):
            for i, char in enumerate(line):
                for gx, gy in _GLYPHS.get(char.upper(), _GLYPHS["?"]):
                    column = i * (FONT_WIDTH + 1) + gx # font pixels from the start of the line
                    left, right = x0 + _round(column * across), x0 + _round((column + 1) * across) - 1
                    for row in range(y + gy * scale, y + (gy + 1) * scale):
                        self._span(row, left, right, color)
            y += (FONT_HEIGHT + 1) * scale
        self._changed()

    def text_size(self, text: str, scale: int = 1, fix_aspect: Optional[bool] = None) -> tuple[int, int]:
        """How many pixels (wide, tall) text() would draw text in: for centring it."""
        if fix_aspect is None: fix_aspect = self.fix_aspect
        return text_size(text, scale, self.pixel_aspect if fix_aspect else 1.0)

    def image(self, pixels: Sequence[Sequence[Optional[Color]]], x: float = 0, y: float = 0) -> None:
        """Copy rows of colors in with their top-left at (x, y). None is see-through."""
        self._begin()
        x, y = _round(x), _round(y)
        for row, values in enumerate(pixels):
            for col, color in enumerate(values):
                if color is not None:
                    self._put(x + col, y + row, check_color(color))
        self._changed()
