import os
import sys

ESC = "\x1b["
RESET = ESC + "0m"

# Border character sets: top-left, top-right, bottom-left, bottom-right, horizontal, vertical
BORDERS = {
    "single":  "┌┐└┘─│",
    "double":  "╔╗╚╝═║",
    "rounded": "╭╮╰╯─│",
    "heavy":   "┏┓┗┛━┃",
    "ascii":   "++++-|",
}

COLORS = {
    "black": 0, "red": 1, "green": 2, "yellow": 3,
    "blue": 4, "magenta": 5, "cyan": 6, "white": 7,
}

# --- Screen / cursor ------------------------------------------------------

def screen_size():
    size = os.get_terminal_size()
    return size.columns, size.lines

def move(x, y):
    """Escape code to move the cursor to column x, row y (0-based)."""
    return f"{ESC}{y + 1};{x + 1}H"

def hide_cursor(): return ESC + "?25l"
def show_cursor(): return ESC + "?25h"
def clear_screen(): return ESC + "2J"

def write(s):
    """Write and flush in one go. Uses the real stdout, so drawing still works
    while sys.stdout is being intercepted."""
    sys.__stdout__.write(s)
    sys.__stdout__.flush()

# --- Styling ----------------------------------------------------------------

def style(fg=None, bg=None, bold=False, underline=False):
    """Escape code for a style. Colors are names from COLORS, prefixed 'bright_' for bright."""
    codes = []
    if bold: codes.append("1")
    if underline: codes.append("4")
    if fg: codes.append(str(_color_code(fg, 30)))
    if bg: codes.append(str(_color_code(bg, 40)))
    return f"{ESC}{';'.join(codes)}m" if codes else ""

def styled(text, **kwargs):
    """Wrap text in a style and reset after it."""
    s = style(**kwargs)
    return f"{s}{text}{RESET}" if s else text

def _color_code(name, base):
    if name.startswith("bright_"): return COLORS[name[7:]] + base + 60
    return COLORS[name] + base

# --- Padding / fitting ------------------------------------------------------

def pad_left(text, width, char=" "):
    """Right-align text in width (padding goes on the left)."""
    return fit(text, width).rjust(width, char)

def pad_right(text, width, char=" "):
    """Left-align text in width (padding goes on the right)."""
    return fit(text, width).ljust(width, char)

def pad_center(text, width, char=" "):
    return fit(text, width).center(width, char)

def fit(text, width, ellipsis="…"):
    """Crop text to width, ending with an ellipsis if it was cut."""
    if len(text) <= width: return text
    if width <= len(ellipsis): return text[:width]
    return text[:width - len(ellipsis)] + ellipsis

def wrap(text, width):
    """Word-wrap text into a list of lines no longer than width."""
    lines = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split(" "):
            while len(word) > width:  # hard-break words longer than a line
                if line:
                    lines.append(line)
                    line = ""
                lines.append(word[:width])
                word = word[width:]
            if not line:
                line = word
            elif len(line) + 1 + len(word) <= width: 
                line += " " + word
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines

# --- Canvas -------------------------------------------------------------------

class Canvas:
    """An off-screen grid of characters. Draw into it, then send it to the
    terminal with a single write via draw_to()."""

    def __init__(self, width, height, fill=" "):
        self.width = width
        self.height = height
        self.chars = [[fill] * width for _ in range(height)]
        self.styles = [[""] * width for _ in range(height)]

    def put(self, x, y, char, style=""):
        """Set one cell. Anything outside the canvas is ignored."""
        if 0 <= x < self.width and 0 <= y < self.height:
            self.chars[y][x] = char
            self.styles[y][x] = style

    def text(self, x, y, text, style=""):
        """Write a string starting at (x, y), clipped at the canvas edge."""
        for i, char in enumerate(text):
            self.put(x + i, y, char, style)

    def fill(self, x=0, y=0, w=None, h=None, char=" ", style=""):
        """Fill a rectangle (the whole canvas by default)."""
        w = self.width if w is None else w
        h = self.height if h is None else h
        for row in range(y, y + h):
            for col in range(x, x + w):
                self.put(col, row, char, style)

    def border(self, x=0, y=0, w=None, h=None, kind="single", style="", title=None):
        """Draw a box outline (around the whole canvas by default)."""
        w = self.width if w is None else w
        h = self.height if h is None else h
        if w < 2 or h < 2:
            return
        tl, tr, bl, br, hz, vt = BORDERS[kind]
        right, bottom = x + w - 1, y + h - 1
        for col in range(x + 1, right):
            self.put(col, y, hz, style)
            self.put(col, bottom, hz, style)
        for row in range(y + 1, bottom):
            self.put(x, row, vt, style)
            self.put(right, row, vt, style)
        self.put(x, y, tl, style)
        self.put(right, y, tr, style)
        self.put(x, bottom, bl, style)
        self.put(right, bottom, br, style)
        if title and w > 4:
            self.text(x + 2, y, fit(f" {title} ", w - 4), style)

    def render(self, x, y):
        """Build the escape string that draws this canvas with its top-left at
        (x, y): one cursor move per line, style codes only where they change."""
        out = []
        for row in range(self.height):
            out.append(move(x, y + row))
            current = ""
            for col in range(self.width):
                s = self.styles[row][col]
                if s != current:
                    out.append(RESET + s)
                    current = s
                out.append(self.chars[row][col])
            if current:
                out.append(RESET)
        return "".join(out)

    def draw_to(self, x, y):
        """Draw the canvas to the terminal in a single write."""
        write(render_frame(self.render(x, y)))

def render_frame(content):
    """Wrap output in synchronized-update codes so terminals that support it
    show the whole frame at once (others ignore the codes)."""
    return ESC + "?2026h" + content + ESC + "?2026l"
