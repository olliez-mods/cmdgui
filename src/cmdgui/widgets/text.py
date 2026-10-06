from __future__ import annotations

from typing import Any, Callable, Optional
from ..shorts import *
from .base import Widget, field, _call, Align

class Text(Widget):
    """Text that wraps to fit."""
    text: str = field(default="", kw_only=False)
    align: Align = "left"
    style: str = "" # escape code from style(), e.g. style(fg="red")
    def draw(self, c):
        pad = {"left": pad_right, "center": pad_center, "right": pad_left}[self.align]
        for i, line in enumerate(wrap(str(self.text), c.width)[:c.height]):
            c.text(0, i, pad(line, c.width), self.style or self.theme("text"))
    def content_size(self):
        lines = str(self.text).split("\n")
        width = min(80, max(text_width(line) for line in lines))
        return width, max(1, len(wrap(str(self.text), width)))


class Label(Text):
    """One line of text, cut off with … if too long."""
    preferred_height = 1
    def draw(self, c):
        pad = {"left": pad_right, "center": pad_center, "right": pad_left}[self.align]
        c.text(0, c.height // 2, pad(str(self.text), c.width), self.style or self.theme("text"))
    def content_size(self):
        return text_width(str(self.text)), 1


def _is_word(char):
    return char.isalnum() or char == "_"

def _word_left(text, i):
    """Where Ctrl+Left goes from i: the start of the word before it."""
    while i > 0 and not _is_word(text[i - 1]): i -= 1
    while i > 0 and _is_word(text[i - 1]): i -= 1
    return i

def _word_right(text, i):
    """Where Ctrl+Right goes from i: the end of the word after it."""
    while i < len(text) and not _is_word(text[i]): i += 1
    while i < len(text) and _is_word(text[i]): i += 1
    return i

def _index_at(text, start, end, x):
    """The index in text[start:end] that's drawn at column x (wide characters take two)."""
    col = 0
    for i in range(start, end):
        col += char_width(text[i])
        if col > x: return i
    return end

def _edit(value, cursor, key, char, line_start, line_end):
    """The editing keys both text boxes share. Returns the new (value, cursor),
    or None if the key isn't one of them. line_start/line_end bound the cursor's line."""
    if(char): return value[:cursor] + char + value[cursor:], cursor + 1
    if(key == "backspace"):
        return (value[:cursor - 1] + value[cursor:], cursor - 1) if cursor > 0 else (value, cursor)
    if(key == "delete"): return value[:cursor] + value[cursor + 1:], cursor
    if(key == "left"): return value, max(0, cursor - 1)
    if(key == "right"): return value, min(len(value), cursor + 1)
    if(key in ("ctrl+left", "alt+left", "alt+b")): return value, _word_left(value, cursor)
    if(key in ("ctrl+right", "alt+right", "alt+f")): return value, _word_right(value, cursor)
    if(key in ("home", "ctrl+a")): return value, line_start
    if(key in ("end", "ctrl+e")): return value, line_end
    if(key in ("ctrl+w", "alt+backspace")): # delete the word before the cursor
        new = _word_left(value, cursor)
        return value[:new] + value[cursor:], new
    if(key == "ctrl+u"): return value[:line_start] + value[cursor:], line_start # delete to the start of the line
    if(key == "ctrl+k"): return value[:cursor] + value[line_end:], cursor        # delete to the end of the line
    return None


class TextInput(Widget):
    """A one-line text box. Click or Tab to it, then type."""
    value: str = field(default="", kw_only=False)
    placeholder: str = ""
    password: bool = False     # show • instead of the text
    keep_history: bool = False # Enter remembers the value, and up/down bring back earlier ones
    submit_callback: Optional[Callable[[str], Any]] = field(default=None, alias="on_submit")
    change_callback: Optional[Callable[[str], Any]] = field(default=None, alias="on_change")
    preferred_width = "5+"
    preferred_height = 1
    border = True
    focusable = True
    captures_text = True
    def init(self):
        self.cursor = 0 # index in value
        self.scroll = 0 # first visible character, when the value is longer than the box
        self.history = [] # submitted values, oldest first (with keep_history)
        self._history_index = None # which one up/down is showing, None while editing a new value
        self._draft = "" # the new value, kept while looking through the history
    def on_submit(self, callback: Callable[[str], Any]): # called with the value when Enter is pressed
        self.submit_callback = callback
    def on_change(self, callback: Callable[[str], Any]): # called with the value after every edit
        self.change_callback = callback

    def _shown(self):
        return "•" * len(self.value) if self.password else self.value
    def _set(self, value, cursor):
        changed = value != self.value
        self.value, self.cursor = value, cursor
        if(changed): _call(self.change_callback, self.value)
    def _recall(self, step):
        """Up (-1) or down (+1) through the history."""
        if(not self.keep_history or not self.history): return
        if(self._history_index is None):
            if(step > 0): return
            self._draft = self.value
            index = len(self.history) - 1
        else:
            index = max(0, self._history_index + step)
        if(index >= len(self.history)):
            self._history_index, value = None, self._draft # past the newest: back to what was being typed
        else:
            self._history_index, value = index, self.history[index]
        self._set(value, len(value))

    def on_input(self, input):
        if(input.type == "mouse_down" and self.mouse_over()):
            self.cursor = _index_at(self._shown(), self.scroll, len(self.value), self.mouse_pos()[0])
            return
        if(input.type != "key"): return
        key, char = input.details["key"], input.details["char"]
        if(key == "enter"):
            if(self.keep_history and self.value and not self.password and self.history[-1:] != [self.value]):
                self.history.append(self.value)
            self._history_index = None
            _call(self.submit_callback, self.value)
        elif(key in ("up", "down")):
            self._recall(-1 if key == "up" else 1)
        else:
            result = _edit(self.value, self.cursor, key, char, 0, len(self.value))
            if(result is None): return
            self._history_index = None
            self._set(*result)

    def draw(self, c):
        shown = self._shown()
        self.cursor = max(0, min(self.cursor, len(shown)))
        # Keep the cursor in view, counting columns (wide characters take two)
        if(self.cursor < self.scroll): self._set_scroll(self.cursor)
        cursor_width = char_width(shown[self.cursor]) if self.cursor < len(shown) else 1
        while(self.scroll < self.cursor and text_width(shown[self.scroll:self.cursor]) + cursor_width > c.width):
            self._set_scroll(self.scroll + 1)
        if(not self.value and not self.focused):
            c.text(0, 0, fit(self.placeholder, c.width), self.theme("dim"))
            return
        c.text(0, 0, shown[self.scroll:self.scroll + c.width])
        if(self.focused):
            char = shown[self.cursor] if self.cursor < len(shown) else " "
            c.put(text_width(shown[self.scroll:self.cursor]), 0, char, self.theme("cursor"))
    def _set_scroll(self, value):
        object.__setattr__(self, "scroll", value) # no redraw, we're already drawing
    def content_size(self):
        return max(20, text_width(self.placeholder) + 1), 1


class TextArea(Widget):
    """A multi-line text box. Long lines wrap. Enter adds a new line."""
    value: str = field(default="", kw_only=False)
    placeholder: str = ""
    change_callback: Optional[Callable[[str], Any]] = field(default=None, alias="on_change")
    preferred_width = "10+"
    preferred_height = "3+"
    border = True
    focusable = True
    captures_text = True
    def init(self):
        self.cursor = 0 # index in value
        self.scroll = 0 # first visible (wrapped) row
        self._follow = True # scroll to the cursor on the next draw
    def on_change(self, callback: Callable[[str], Any]): # called with the value after every edit
        self.change_callback = callback

    def _rows(self, width):
        """The wrapped rows as (start, end) indexes into value. A line that exactly fills
        its last row gets an extra empty row, so the cursor has somewhere to go."""
        rows, start, width = [], 0, max(1, width)
        for line in self.value.split("\n"):
            row_start, col = 0, 0
            for i, char in enumerate(line):
                w = char_width(char)
                if(col + w > width and i > row_start): # doesn't fit: start a new row
                    rows.append((start + row_start, start + i))
                    row_start, col = i, 0
                col += w
            rows.append((start + row_start, start + len(line)))
            if(line and col >= width):
                rows.append((start + len(line), start + len(line)))
            start += len(line) + 1
        return rows
    def _cursor_row(self, rows):
        """Which row the cursor is on, and its column in that row."""
        for i, (start, end) in enumerate(rows):
            next_start = rows[i + 1][0] if i + 1 < len(rows) else None
            if start <= self.cursor <= end and next_start != self.cursor:
                return i, text_width(self.value[start:self.cursor])
        return len(rows) - 1, 0

    def on_input(self, input):
        if(input.type == "mouse_scroll" and self.mouse_over()):
            step = -1 if input.details["direction"] == "up" else 1
            self.scroll = max(0, min(len(self._rows(self.width)) - self.height, self.scroll + step))
            return
        if(input.type == "mouse_down" and self.mouse_over()):
            rows = self._rows(self.width)
            x, y = self.mouse_pos()
            start, end = rows[min(len(rows) - 1, self.scroll + y)]
            self.cursor = _index_at(self.value, start, end, x)
            return
        if(input.type != "key"): return
        key, char = input.details["key"], input.details["char"]
        value, cursor = self.value, self.cursor
        line_start = value.rfind("\n", 0, cursor) + 1
        line_end = value.find("\n", cursor) % (len(value) + 1) # -1 (last line) becomes len(value)
        if(key == "enter"):
            value, cursor = value[:cursor] + "\n" + value[cursor:], cursor + 1
        elif(key in ("up", "down", "page_up", "page_down")):
            rows = self._rows(self.width)
            row, x = self._cursor_row(rows)
            step = {"up": -1, "down": 1, "page_up": -self.height, "page_down": self.height}[key]
            start, end = rows[max(0, min(len(rows) - 1, row + step))]
            cursor = _index_at(value, start, end, x)
        elif(key == "ctrl+home"): cursor = 0
        elif(key == "ctrl+end"): cursor = len(value)
        else:
            result = _edit(value, cursor, key, char, line_start, line_end)
            if(result is None): return
            value, cursor = result
        changed = value != self.value
        self._follow = True
        self.value, self.cursor = value, cursor
        if(changed): _call(self.change_callback, self.value)

    def draw(self, c):
        self.cursor = max(0, min(self.cursor, len(self.value)))
        rows = self._rows(c.width)
        row, x = self._cursor_row(rows)
        if(self._follow): # keep the cursor in view
            if(row < self.scroll): self._set_scroll(row)
            if(row >= self.scroll + c.height): self._set_scroll(row - c.height + 1)
            self._follow = False
        self._set_scroll(max(0, min(self.scroll, len(rows) - c.height)))
        if(not self.value and not self.focused):
            for i, line in enumerate(wrap(self.placeholder, c.width)[:c.height]):
                c.text(0, i, line, self.theme("dim"))
            return
        for i, (start, end) in enumerate(rows[self.scroll:self.scroll + c.height]):
            c.text(0, i, self.value[start:end])
        if(self.focused and self.scroll <= row < self.scroll + c.height):
            char = self.value[self.cursor] if self.cursor < len(self.value) and self.value[self.cursor] != "\n" else " "
            c.put(x, row - self.scroll, char, self.theme("cursor"))
    def _set_scroll(self, value):
        object.__setattr__(self, "scroll", value) # no redraw, we're already drawing
    def content_size(self):
        return 30, 5
