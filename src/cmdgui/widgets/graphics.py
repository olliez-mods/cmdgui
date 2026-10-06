from __future__ import annotations

from contextlib import nullcontext
from typing import TYPE_CHECKING, Any, Callable, Literal, Optional
from ..shorts import *
from ..shorts import COLORS, EXTRA_COLORS
from ..inputs import mouse
from ..raster import Raster, check_color
from .base import Widget, field, _call

Mode = Literal["half", "quad", "braille"]
# Pixels per cell, across and down
SCALES = {"half": (1, 2), "quad": (2, 2), "braille": (2, 4)}


class Graphics(Widget, Raster):
    """Draw in pixels: lines, shapes, curves. Several pixels fit in each character cell:

        "half"     1x2, every pixel its own color, square pixels (the default)
        "quad"     2x2, at most two colors per cell (others snap to the nearer one)
        "braille"  2x4 dots, one color per cell, for charts and line drawings

    Draw any time and the picture stays (when the widget is resized, what fits is
    kept). Or pass on_paint=fn(graphics), which draws the whole picture: it's called
    on a cleared widget whenever the size changes, and when you call repaint().
    For animation, view.every(1/30, graphics.repaint)."""
    mode: Mode = "half"
    background: Optional[Color] = None # shown where nothing is drawn; None is the terminal's own
    paint_callback: Optional[Callable[["Graphics"], Any]] = field(default=None, alias="on_paint")
    click_callback: Optional[Callable[[int, int], Any]] = field(default=None, alias="on_click")
    drag_callback: Optional[Callable[[int, int], Any]] = field(default=None, alias="on_drag")
    border = True

    def init(self):
        self._init_pixels()
        self._repaint = True # call on_paint on the next draw
        self._dragging = False

    if not TYPE_CHECKING:
        def __setattr__(self, key, value):
            # Check these now, rather than crash the view when it draws
            if key == "background":
                value = check_color(value)
            elif key == "mode" and value not in SCALES:
                raise ValueError(f"unknown mode {value!r}: use {', '.join(map(repr, SCALES))}")
            super().__setattr__(key, value)

    def on_paint(self, callback: Optional[Callable[["Graphics"], Any]]):
        self.paint_callback = callback
        self.repaint()
    def on_click(self, callback: Callable[[int, int], Any]): # called with the pixel (x, y) on a click
        self.click_callback = callback
    def on_drag(self, callback: Callable[[int, int], Any]): # called with the pixel (x, y) as the mouse moves with the button held
        self.drag_callback = callback

    def repaint(self) -> None:
        """Clear and call on_paint on the next frame."""
        self._repaint = True
        self.refresh()

    def batch(self):
        """Draw several things with no frame shown in between, from another thread:
            with graphics.batch():
                graphics.clear()
                graphics.circle(...)
        Not needed in callbacks and timers, which already run between frames."""
        return self.view.lock if self.view else nullcontext()

    @property
    def pixel_aspect(self) -> float:
        """How many times taller than wide a pixel is: 1 for half and braille, 2 for
        quad (a cell is about twice as tall as it is wide). For a round circle in any
        mode: ellipse(x, y, r, r / g.pixel_aspect, color)."""
        sx, sy = SCALES[self.mode]
        return 2 * sx / sy

    def mouse_pixel(self) -> tuple[int, int]:
        """The pixel at the top-left of the cell the mouse is over."""
        sx, sy = SCALES[self.mode]
        x, y = self.mouse_pos()
        return x * sx, y * sy

    def copy(self):
        new = super().copy()
        new._rows = [row[:] for row in self._rows] # its own pixels, not shared rows
        return new

    # --- Raster hooks ---
    def _begin(self):
        """Match the pixels to the widget's size and mode."""
        sx, sy = SCALES[self.mode]
        size = (max(0, self.width) * sx, max(0, self.height) * sy)
        if size != (self._pw, self._ph):
            self._resize_pixels(*size)
            self._repaint = True
    def _changed(self):
        self.refresh()

    def on_input(self, input):
        if(input.type == "mouse_down" and input.details["button"] == 0 and self.mouse_over()):
            self._dragging = True
            _call(self.click_callback, *self.mouse_pixel())
        elif(input.type == "mouse_move" and self._dragging and mouse.is_down(0)):
            if(mouse.moved and self.mouse_over()): _call(self.drag_callback, *self.mouse_pixel())
        elif(input.type in ("mouse_up", "mouse_move")):
            self._dragging = False

    def draw(self, c):
        self._begin()
        if(self._repaint):
            self._repaint = False
            if(self.paint_callback):
                self._rows = [[None] * self._pw for _ in range(self._ph)]
                self.paint_callback(self)
        ENCODERS[self.mode](self._rows, c, self.background)

    def content_size(self):
        return 32, 10


# --- Turning pixels into characters ---------------------------------------------

_styles = {} # (fg, bg) -> style string

def _style(fg, bg):
    s = _styles.get((fg, bg))
    if s is None:
        if len(_styles) > 4096: _styles.clear() # lots of different colors, like a gradient
        s = _styles[(fg, bg)] = style(fg=fg, bg=bg)
    return s


def _draw_half(rows, c, bg):
    """One pixel in the top half of each cell, one in the bottom: ▀ with the top
    pixel's color as the foreground, the bottom one's as the background."""
    for cy in range(c.height):
        top_row, bottom_row = rows[2 * cy], rows[2 * cy + 1]
        chars, styles = c.chars[cy], c.styles[cy]
        for cx in range(c.width):
            top, bottom = top_row[cx], bottom_row[cx]
            if top is None: top = bg
            if bottom is None: bottom = bg
            if top == bottom:
                chars[cx], styles[cx] = " ", _style(None, top)
            elif bottom is None:
                chars[cx], styles[cx] = "▀", _style(top, None)
            elif top is None:
                chars[cx], styles[cx] = "▄", _style(bottom, None)
            else:
                chars[cx], styles[cx] = "▀", _style(top, bottom)


# Indexed by which quarters are the foreground: 1 top-left, 2 top-right, 4 bottom-left, 8 bottom-right
QUADRANTS = " ▘▝▀▖▌▞▛▗▚▐▜▄▙▟█"

def _draw_quad(rows, c, bg):
    for cy in range(c.height):
        top_row, bottom_row = rows[2 * cy], rows[2 * cy + 1]
        chars, styles = c.chars[cy], c.styles[cy]
        for cx in range(c.width):
            x = 2 * cx
            cell = [top_row[x], top_row[x + 1], bottom_row[x], bottom_row[x + 1]]
            cell = [bg if p is None else p for p in cell]
            fg, back, mask = _two_colors(cell)
            if fg == back:
                chars[cx], styles[cx] = " ", _style(None, fg)
                continue
            if fg is None: # nothing can be drawn in the terminal's own background: swap
                fg, back, mask = back, None, mask ^ 15
            chars[cx], styles[cx] = QUADRANTS[mask], _style(fg, back)

def _two_colors(cell):
    """Two colors for a cell's pixels, and a bit for each pixel that's the first.
    With more than two, the two most common win and the others snap to the nearer."""
    a = cell[0]
    b = next((p for p in cell if p != a), a)
    if any(p != a and p != b for p in cell):
        counts = {}
        for p in cell: counts[p] = counts.get(p, 0) + 1
        a, b = sorted(counts, key=counts.get, reverse=True)[:2] # ties go to the first seen
        ra, rb = _rgb(a), _rgb(b)
        cell = [p if p == a or p == b else a if _distance(_rgb(p), ra) <= _distance(_rgb(p), rb) else b
                for p in cell]
    mask = 0
    for i, p in enumerate(cell):
        if p == a: mask |= 1 << i
    return a, b, mask


# Braille dot bits by [row][column]
BRAILLE_BITS = ((0x01, 0x08), (0x02, 0x10), (0x04, 0x20), (0x40, 0x80))

def _draw_braille(rows, c, bg):
    """A dot for every pixel that isn't empty (or the background), in the cell's
    most common color."""
    for cy in range(c.height):
        cell_rows = rows[4 * cy:4 * cy + 4]
        chars, styles = c.chars[cy], c.styles[cy]
        for cx in range(c.width):
            x, mask, counts = 2 * cx, 0, {}
            for row, bits in zip(cell_rows, BRAILLE_BITS):
                for dx in (0, 1):
                    p = row[x + dx]
                    if p is not None and p != bg:
                        mask |= bits[dx]
                        counts[p] = counts.get(p, 0) + 1
            if mask:
                chars[cx], styles[cx] = chr(0x2800 + mask), _style(max(counts, key=counts.get), bg)
            else:
                chars[cx], styles[cx] = " ", _style(None, bg)

ENCODERS = {"half": _draw_half, "quad": _draw_quad, "braille": _draw_braille}


# --- Colors as RGB, to find the nearer of two -----------------------------------

# The xterm defaults for the 16 basic colors; terminals' themes vary, so it's a guess
BASIC_RGB = [(0, 0, 0), (205, 0, 0), (0, 205, 0), (205, 205, 0), (0, 0, 238), (205, 0, 205),
             (0, 205, 205), (229, 229, 229), (127, 127, 127), (255, 0, 0), (0, 255, 0),
             (255, 255, 0), (92, 92, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255)]
CUBE = (0, 95, 135, 175, 215, 255)

_rgb_cache = {}

def _rgb(color):
    """A color as (r, g, b). None (the terminal's background) is taken as black."""
    if color not in _rgb_cache:
        _rgb_cache[color] = _to_rgb(color)
    return _rgb_cache[color]

def _to_rgb(color):
    if color is None: return (0, 0, 0)
    if isinstance(color, tuple): return color
    if isinstance(color, int):
        if color < 16: return BASIC_RGB[color]
        if color < 232:
            n = color - 16
            return CUBE[n // 36], CUBE[n // 6 % 6], CUBE[n % 6]
        gray = 8 + 10 * (color - 232)
        return gray, gray, gray
    name = color.lower().replace("grey", "gray").replace(" ", "_")
    if name.startswith("#"):
        return int(name[1:3], 16), int(name[3:5], 16), int(name[5:7], 16)
    if name in COLORS: return BASIC_RGB[COLORS[name]]
    if name.startswith("bright_"): return BASIC_RGB[COLORS[name[7:]] + 8]
    return _to_rgb(EXTRA_COLORS[name])

def _distance(a, b):
    # Weighted towards green, which the eye is most sensitive to
    return 2 * (a[0] - b[0]) ** 2 + 4 * (a[1] - b[1]) ** 2 + 3 * (a[2] - b[2]) ** 2
