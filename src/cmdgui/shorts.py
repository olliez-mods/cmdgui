import os
import sys
import unicodedata
from typing import Literal, Optional, Tuple, Union, get_args

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

# Line-drawing characters by which directions they connect, for borders that
# meet and cross: bits are UP, DOWN, LEFT, RIGHT
UP, DOWN, LEFT, RIGHT = 1, 2, 4, 8
LINE_CHARS = {
    LEFT: "─", RIGHT: "─", LEFT | RIGHT: "─",
    UP: "│", DOWN: "│", UP | DOWN: "│",
    DOWN | RIGHT: "┌", DOWN | LEFT: "┐", UP | RIGHT: "└", UP | LEFT: "┘",
    UP | DOWN | RIGHT: "├", UP | DOWN | LEFT: "┤",
    DOWN | LEFT | RIGHT: "┬", UP | LEFT | RIGHT: "┴",
    UP | DOWN | LEFT | RIGHT: "┼",
}

# The basic colors (and 'bright_' versions) use the terminal's own palette, so
# they match the user's theme
COLORS = {
    "black": 0, "red": 1, "green": 2, "yellow": 3,
    "blue": 4, "magenta": 5, "cyan": 6, "white": 7,
}

# More colors, as numbers in the 256-color palette (supported by nearly every terminal).
# "grey" works wherever "gray" does.
EXTRA_COLORS = {
    # reds and pinks
    "dark_red": 88, "maroon": 52, "crimson": 161, "scarlet": 196, "coral": 203,
    "salmon": 209, "rose": 211, "pink": 218, "hot_pink": 205, "deep_pink": 198,
    # oranges, yellows and browns
    "orange": 208, "dark_orange": 166, "amber": 214, "gold": 220, "lemon": 227,
    "cream": 229, "peach": 216, "tan": 180, "khaki": 186, "brown": 94,
    "rust": 130, "copper": 173,
    # greens
    "lime": 118, "chartreuse": 112, "olive": 100, "dark_green": 28, "forest": 22,
    "emerald": 35, "sea_green": 72, "mint": 121, "pale_green": 157,
    # blues and cyans
    "teal": 30, "turquoise": 44, "aqua": 51, "sky": 117, "light_blue": 153,
    "steel_blue": 67, "cornflower": 69, "royal_blue": 63, "dodger_blue": 33,
    "dark_blue": 19, "navy": 17, "slate": 60,
    # purples
    "indigo": 54, "purple": 93, "dark_purple": 53, "violet": 177, "lavender": 183,
    "plum": 176, "orchid": 170, "fuchsia": 201,
    # grays
    "charcoal": 236, "dark_gray": 238, "gray": 244, "silver": 249,
    "light_gray": 252, "snow": 255,
}

# Every color name, so editors can autocomplete style(fg="...") and catch typos.
# Keep in step with COLORS and EXTRA_COLORS (checked below).
ColorName = Literal[
    "black", "red", "green", "yellow", "blue", "magenta", "cyan", "white", "bright_black",
    "bright_red", "bright_green", "bright_yellow", "bright_blue", "bright_magenta",
    "bright_cyan", "bright_white",
    "dark_red", "maroon", "crimson", "scarlet", "coral", "salmon", "rose", "pink",
    "hot_pink", "deep_pink", "orange", "dark_orange", "amber", "gold", "lemon", "cream",
    "peach", "tan", "khaki", "brown", "rust", "copper", "lime", "chartreuse", "olive",
    "dark_green", "forest", "emerald", "sea_green", "mint", "pale_green", "teal",
    "turquoise", "aqua", "sky", "light_blue", "steel_blue", "cornflower", "royal_blue",
    "dodger_blue", "dark_blue", "navy", "slate", "indigo", "purple", "dark_purple",
    "violet", "lavender", "plum", "orchid", "fuchsia", "charcoal", "dark_gray", "gray",
    "silver", "light_gray", "snow",
]
# A color: a name, a 256-color palette number, "#rrggbb", or (r, g, b)
Color = Union[ColorName, str, int, Tuple[int, int, int]]
assert set(get_args(ColorName)) == set(COLORS) | {"bright_" + c for c in COLORS} | set(EXTRA_COLORS), \
    "ColorName is out of date with COLORS / EXTRA_COLORS"

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

def style(fg: Optional[Color] = None, bg: Optional[Color] = None, bold: bool = False, dim: bool = False,
          italic: bool = False, underline: bool = False, reverse: bool = False) -> str:
    """Escape code for a style. A color can be:
        a name from COLORS, or 'bright_' + one of those: "red", "bright_red"
        a name from EXTRA_COLORS: "orange", "teal", "lavender"
        a number in the 256-color palette: 208
        a hex string or (r, g, b) for exact colors, if the terminal has true color: "#ff8800" """
    codes = []
    if bold: codes.append("1")
    if dim: codes.append("2")
    if italic: codes.append("3")
    if underline: codes.append("4")
    if reverse: codes.append("7")
    if fg is not None: codes.append(_color_code(fg, 30))
    if bg is not None: codes.append(_color_code(bg, 40))
    return f"{ESC}{';'.join(codes)}m" if codes else ""

def styled(text, **kwargs):
    """Wrap text in a style and reset after it."""
    s = style(**kwargs)
    return f"{s}{text}{RESET}" if s else text

def _color_code(color, base):
    """The SGR code for a color, base is 30 for the foreground or 40 for the background."""
    extended = base + 8 # 38 / 48 start a 256-color or true color code
    if isinstance(color, int) and not isinstance(color, bool) and 0 <= color <= 255:
        return f"{extended};5;{color}"
    if isinstance(color, (tuple, list)) and len(color) == 3:
        return f"{extended};2;" + ";".join(str(max(0, min(255, int(v)))) for v in color)
    if isinstance(color, str):
        name = color.lower().replace("grey", "gray").replace(" ", "_")
        if name.startswith("#") and len(name) == 7:
            try:
                return f"{extended};2;{int(name[1:3], 16)};{int(name[3:5], 16)};{int(name[5:7], 16)}"
            except ValueError:
                pass
        elif name in COLORS:
            return str(COLORS[name] + base)
        elif name.startswith("bright_") and name[7:] in COLORS:
            return str(COLORS[name[7:]] + base + 60)
        elif name in EXTRA_COLORS:
            return f"{extended};5;{EXTRA_COLORS[name]}"
    raise ValueError(f"unknown color {color!r}: use a name from COLORS or EXTRA_COLORS "
                     f"(with 'bright_' for the basic ones), 0-255, '#rrggbb' or (r, g, b)")

# --- Text width -------------------------------------------------------------
# Emoji and CJK characters take two columns, combining accents take none.

def char_width(char):
    if unicodedata.combining(char) or char in "\u200b\u200d\ufe0f":
        return 0
    if unicodedata.east_asian_width(char) in ("W", "F"):
        return 2
    return 1

def text_width(text):
    """How many columns text takes on screen."""
    return sum(char_width(c) for c in text)

def take(text, width):
    """The longest start of text that fits in width columns."""
    used = 0
    for i, char in enumerate(text):
        used += char_width(char)
        if used > width:
            return text[:i]
    return text

# --- Padding / fitting ------------------------------------------------------

def pad_left(text, width, char=" "):
    """Right-align text in width (padding goes on the left)."""
    text = fit(text, width)
    return char * (width - text_width(text)) + text

def pad_right(text, width, char=" "):
    """Left-align text in width (padding goes on the right)."""
    text = fit(text, width)
    return text + char * (width - text_width(text))

def pad_center(text, width, char=" "):
    text = fit(text, width)
    space = width - text_width(text)
    return char * (space // 2) + text + char * (space - space // 2)

def fit(text, width, ellipsis="…"):
    """Crop text to width, ending with an ellipsis if it was cut."""
    if text_width(text) <= width: return text
    if width <= len(ellipsis): return take(text, width)
    return take(text, width - len(ellipsis)) + ellipsis

def wrap(text, width):
    """Word-wrap text into a list of lines no longer than width."""
    if width <= 0: return []
    lines = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split(" "):
            while text_width(word) > width:  # hard-break words longer than a line
                if line:
                    lines.append(line)
                    line = ""
                part = take(word, width) or word[0]
                lines.append(part)
                word = word[len(part):]
            if not line:
                line = word
            elif text_width(line) + 1 + text_width(word) <= width:
                line += " " + word
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines

# --- Canvas -------------------------------------------------------------------

class Canvas:
    """An off-screen grid of characters. Draw into it, then send it to the
    terminal with a single write via draw_to().

    A wide character takes two cells: the character, then "" in the next one."""

    def __init__(self, width, height, fill=" "):
        self.width = width
        self.height = height
        self.chars = [[fill] * width for _ in range(height)]
        self.styles = [[""] * width for _ in range(height)]

    def put(self, x, y, char, style=""):
        """Set one cell. Anything outside the canvas is ignored.
        Returns how many columns the character took."""
        width = char_width(char)
        if width == 0 or not (0 <= x < self.width and 0 <= y < self.height):
            return width
        if width == 2 and x + 1 >= self.width:
            char, width = " ", 1  # no room for the second half
        self._clear_wide(x, y)
        self.chars[y][x] = char
        self.styles[y][x] = style
        if width == 2:
            self._clear_wide(x + 1, y)
            self.chars[y][x + 1] = ""
            self.styles[y][x + 1] = style
        return width

    def _clear_wide(self, x, y):
        """Before overwriting a cell, blank out the other half of any wide character in it."""
        row = self.chars[y]
        if row[x] == "" and x > 0:
            row[x - 1] = " "
        elif x + 1 < self.width and row[x + 1] == "":
            row[x + 1] = " "

    def text(self, x, y, text, style=""):
        """Write a string starting at (x, y), clipped at the canvas edge.
        Returns the x just after the text."""
        for char in text:
            x += self.put(x, y, char, style)
        return x

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

    def copy(self):
        c = Canvas(0, 0)
        c.width, c.height = self.width, self.height
        c.chars = [row[:] for row in self.chars]
        c.styles = [row[:] for row in self.styles]
        return c

    def blit(self, other, x, y):
        """Copy another canvas onto this one with its top-left at (x, y), clipped."""
        for row in range(other.height):
            ty = y + row
            if not 0 <= ty < self.height:
                continue
            for col in range(other.width):
                tx = x + col
                if 0 <= tx < self.width:
                    self.chars[ty][tx] = other.chars[row][col]
                    self.styles[ty][tx] = other.styles[row][col]
            # Don't leave half a wide character at the clipped edges
            if 0 <= x < self.width and self.chars[ty][x] == "":
                self.chars[ty][x] = " "
            end = x + other.width
            if 0 <= end < self.width and self.chars[ty][end] == "" and self.chars[ty][end - 1] != "" \
                    and char_width(self.chars[ty][end - 1]) != 2:
                self.chars[ty][end] = " "

    def _run(self, row, start, end):
        """Escape string for cells start..end of a row, style codes only where they change."""
        out = []
        current = ""
        for col in range(start, end + 1):
            char = self.chars[row][col]
            if char == "":
                continue  # second half of a wide character
            s = self.styles[row][col]
            if s != current:
                out.append(RESET + s)
                current = s
            out.append(char)
        if current:
            out.append(RESET)
        return "".join(out)

    def render(self, x, y):
        """Build the escape string that draws this canvas with its top-left at
        (x, y): one cursor move per line, style codes only where they change."""
        return "".join(move(x, y + row) + self._run(row, 0, self.width - 1) for row in range(self.height))

    def diff(self, old):
        """Escape string that turns old (what's on screen) into this canvas,
        touching only the cells that changed. old=None draws everything."""
        if old is None or (old.width, old.height) != (self.width, self.height):
            return self.render(0, 0)
        out = []
        for y in range(self.height):
            new_chars, new_styles = self.chars[y], self.styles[y]
            old_chars, old_styles = old.chars[y], old.styles[y]
            x = 0
            while x < self.width:
                if new_chars[x] == old_chars[x] and new_styles[x] == old_styles[x]:
                    x += 1
                    continue
                start = x - 1 if new_chars[x] == "" and x > 0 else x
                end, gap = x, 0
                x += 1
                # Keep going through small unchanged gaps, cheaper than another cursor move
                while x < self.width and gap <= 3:
                    if new_chars[x] == old_chars[x] and new_styles[x] == old_styles[x]:
                        gap += 1
                    else:
                        gap, end = 0, x
                    x += 1
                if end + 1 < self.width and new_chars[end + 1] == "":
                    end += 1
                out.append(move(start, y) + self._run(y, start, end))
                x = end + 1
        return "".join(out)

    def draw_to(self, x, y):
        """Draw the canvas to the terminal in a single write."""
        write(render_frame(self.render(x, y)))

def render_frame(content):
    """Wrap output in synchronized-update codes so terminals that support it
    show the whole frame at once (others ignore the codes)."""
    return ESC + "?2026h" + content + ESC + "?2026l"
