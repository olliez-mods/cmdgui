import os
import sys
import unicodedata

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

def style(fg=None, bg=None, bold=False, dim=False, italic=False, underline=False, reverse=False):
    """Escape code for a style. Colors are names from COLORS, prefixed 'bright_' for bright."""
    codes = []
    if bold: codes.append("1")
    if dim: codes.append("2")
    if italic: codes.append("3")
    if underline: codes.append("4")
    if reverse: codes.append("7")
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
