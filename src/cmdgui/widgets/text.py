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


class TextInput(Widget):
    """A one-line text box. Click or Tab to it, then type."""
    value: str = field(default="", kw_only=False)
    placeholder: str = ""
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
    def on_submit(self, callback: Callable[[str], Any]): # called with the value when Enter is pressed
        self.submit_callback = callback
    def on_change(self, callback: Callable[[str], Any]): # called with the value after every edit
        self.change_callback = callback

    def on_input(self, input):
        if(input.type == "mouse_down" and self.mouse_over()):
            self.cursor = min(len(self.value), self.scroll + self.mouse_pos()[0])
            return
        if(input.type != "key"): return
        key, char = input.details["key"], input.details["char"]
        value, cursor = self.value, self.cursor
        if(char):
            value = value[:cursor] + char + value[cursor:]
            cursor += 1
        elif(key == "backspace" and cursor > 0):
            value = value[:cursor - 1] + value[cursor:]
            cursor -= 1
        elif(key == "delete"):
            value = value[:cursor] + value[cursor + 1:]
        elif(key == "left"): cursor = max(0, cursor - 1)
        elif(key == "right"): cursor = min(len(value), cursor + 1)
        elif(key in ("home", "ctrl+a")): cursor = 0
        elif(key in ("end", "ctrl+e")): cursor = len(value)
        elif(key == "enter"):
            _call(self.submit_callback, self.value)
            return
        else:
            return
        changed = value != self.value
        self.value, self.cursor = value, cursor
        if(changed): _call(self.change_callback, self.value)

    def draw(self, c):
        self.cursor = max(0, min(self.cursor, len(self.value)))
        # Keep the cursor in view
        if(self.cursor < self.scroll): self._set_scroll(self.cursor)
        if(self.cursor >= self.scroll + c.width): self._set_scroll(self.cursor - c.width + 1)
        if(not self.value and not self.focused):
            c.text(0, 0, fit(self.placeholder, c.width), self.theme("dim"))
            return
        c.text(0, 0, self.value[self.scroll:self.scroll + c.width])
        if(self.focused):
            x = self.cursor - self.scroll
            char = self.value[self.cursor] if self.cursor < len(self.value) else " "
            c.put(x, 0, char, self.theme("cursor"))
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
        """The wrapped rows as (start, end) indexes into value. A line whose length
        is a multiple of width gets an extra empty row, so the cursor has somewhere to go."""
        rows, start, width = [], 0, max(1, width)
        for line in self.value.split("\n"):
            for col in range(0, len(line) + 1, width):
                rows.append((start + col, start + min(col + width, len(line))))
            start += len(line) + 1
        return rows
    def _cursor_row(self, rows):
        """Which row the cursor is on, and its x in that row."""
        for i, (start, end) in enumerate(rows):
            next_start = rows[i + 1][0] if i + 1 < len(rows) else None
            if start <= self.cursor <= end and next_start != self.cursor:
                return i, self.cursor - start
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
            self.cursor = min(end, start + x)
            return
        if(input.type != "key"): return
        key, char = input.details["key"], input.details["char"]
        value, cursor = self.value, self.cursor
        rows = self._rows(self.width)
        row, x = self._cursor_row(rows)
        line_start = value.rfind("\n", 0, cursor) + 1
        line_end = value.find("\n", cursor) % (len(value) + 1) # -1 (last line) becomes len(value)
        if(char or key == "enter"):
            char = char or "\n"
            value = value[:cursor] + char + value[cursor:]
            cursor += 1
        elif(key == "backspace" and cursor > 0):
            value = value[:cursor - 1] + value[cursor:]
            cursor -= 1
        elif(key == "delete"):
            value = value[:cursor] + value[cursor + 1:]
        elif(key == "left"): cursor = max(0, cursor - 1)
        elif(key == "right"): cursor = min(len(value), cursor + 1)
        elif(key in ("up", "down", "page_up", "page_down")):
            step = {"up": -1, "down": 1, "page_up": -self.height, "page_down": self.height}[key]
            start, end = rows[max(0, min(len(rows) - 1, row + step))]
            cursor = min(end, start + x)
        elif(key in ("home", "ctrl+a")): cursor = line_start
        elif(key in ("end", "ctrl+e")): cursor = line_end
        elif(key == "ctrl+home"): cursor = 0
        elif(key == "ctrl+end"): cursor = len(value)
        else:
            return
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
