from __future__ import annotations

from ..shorts import *
from ..inputs import mouse
from .base import Widget

class Stdout(Widget):
    """Shows everything printed (and stderr, in red). Scroll with the mouse wheel, or
    the arrow keys, Page Up/Down and Home/End when focused. End follows new output again."""
    max_lines: int = 500
    border = True
    preferred_width = "10+"
    preferred_height = "3+"
    focusable = True
    def init(self):
        self.lines = [["", ""]] # [text, style]
        self.scroll = 0 # wrapped lines up from the bottom
    def on_input(self, input):
        if(input.type in ("stdout", "stderr")):
            self.write(input.details["text"], error=input.type == "stderr")
        elif(input.type == "mouse_scroll" and self.mouse_over()):
            step = 1 if input.details["direction"] == "up" else -1
            self._set_scroll(max(0, self.scroll + step))
            self.refresh()
        elif(input.type == "key"):
            page = max(1, self.height - 1)
            moves = {"up": 1, "down": -1, "page_up": page, "page_down": -page,
                     "home": 10 ** 9, "end": -10 ** 9} # draw() stops it at the top
            if(input.details["key"] in moves):
                self._set_scroll(max(0, self.scroll + moves[input.details["key"]]))
                self.refresh()
    def _set_scroll(self, value):
        object.__setattr__(self, "scroll", value)
    def clear(self):
        """Remove everything shown so far."""
        self.lines = [["", ""]]
        self._set_scroll(0)
    def write(self, text, error=False):
        """Add raw text to this widget only (not the real stdout)."""
        s = self.theme("error") if error else ""
        # Text can arrive mid-line, so the first part continues the last line
        parts = text.split("\n")
        self.lines[-1][0] += parts[0]
        if(parts[0] and s): self.lines[-1][1] = s
        self.lines.extend([part, s] for part in parts[1:])
        del self.lines[:-self.max_lines]
        if(self.scroll): self._set_scroll(self.scroll + len(parts) - 1) # stay put while scrolled up
        self.refresh()
    def print(self, *values, sep=" ", end="\n", error=False):
        """Like print(), but only shows up in this widget."""
        sep = " " if sep is None else sep
        end = "\n" if end is None else end
        self.write(sep.join(map(str, values)) + end, error)
    def content_size(self):
        return 40, 8
    def draw(self, c):
        lines = self.lines[:-1] if self.lines[-1][0] == "" else self.lines # skip empty line after a trailing \n
        wrapped = [(part, s) for text, s in lines for part in wrap(text, c.width)]
        self._set_scroll(min(self.scroll, max(0, len(wrapped) - c.height)))
        end = len(wrapped) - self.scroll
        for i, (line, s) in enumerate(wrapped[max(0, end - c.height):end]):
            c.text(0, i, line, s)
        if(self.scroll):
            label = f" ↓ {self.scroll} more "
            c.text(max(0, c.width - len(label)), c.height - 1, label, self.theme("dim"))


class DrawMouse(Widget):
    border = True
    def init(self):
        self.tiles:dict[tuple[int,int], bool] = {}
    def on_input(self, input):
        if(not input.type.startswith("mouse")): return

        # Toggle a tile on click, and on each new cell while dragging
        if(self.mouse_over() and (input.type == "mouse_down" or (mouse.is_down() and mouse.moved))):
            pos = self.mouse_pos()
            if(self.tiles.get(pos)): self.tiles.pop(pos)
            else: self.tiles[pos] = True

        self.refresh()
    def draw(self, c):
        for key, _ in self.tiles.items():
            x,y = key
            c.put(x, y, "#")
        x, y = self.mouse_pos()
        c.put(x, y, "X" if mouse.is_down() else "O")
