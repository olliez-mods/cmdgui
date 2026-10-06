from __future__ import annotations

from typing import Any, Callable, Optional
from ..shorts import *
from .base import Widget, field, _call

class Menu(Widget):
    """A list to pick from with the arrow keys and Enter, or a click."""
    items: list = field(default_factory=list, kw_only=False)
    selected: int = 0
    select_callback: Optional[Callable[[int, Any], Any]] = field(default=None, alias="on_select")
    border = True
    focusable = True
    def init(self):
        self.scroll = 0
        self.hovered = None
    def on_select(self, callback: Callable[[int, Any], Any]): # called with (index, item) on Enter or click
        self.select_callback = callback
    def _choose(self):
        if(0 <= self.selected < len(self.items)):
            _call(self.select_callback, self.selected, self.items[self.selected])

    def on_input(self, input):
        if(input.type == "key"):
            key = input.details["key"]
            moves = {"up": -1, "down": 1, "page_up": -self.height, "page_down": self.height,
                     "home": -len(self.items), "end": len(self.items)}
            if(key in moves and self.items):
                self.selected = max(0, min(len(self.items) - 1, self.selected + moves[key]))
            elif(key in ("enter", "space")):
                self._choose()
        elif(input.type == "mouse_down" and self.mouse_over()):
            index = self.scroll + self.mouse_pos()[1]
            if(index < len(self.items)):
                self.selected = index
                self._choose()
        elif(input.type == "mouse_scroll" and self.mouse_over()):
            step = -1 if input.details["direction"] == "up" else 1
            self.scroll = max(0, min(max(0, len(self.items) - self.height), self.scroll + step))
        elif(input.type == "mouse_move"):
            self.hovered = None
            if(not self.mouse_over()): return
            index = self.scroll + self.mouse_pos()[1]
            if(index < len(self.items)):
                self.hovered = index
    def draw(self, c):
        # Keep the selection in view
        if(self.selected < self.scroll): object.__setattr__(self, "scroll", self.selected)
        if(self.selected >= self.scroll + c.height): object.__setattr__(self, "scroll", self.selected - c.height + 1)
        for row, item in enumerate(self.items[self.scroll:self.scroll + c.height]):
            index = self.scroll + row
            s = ""
            if(index == self.selected):
                s = self.theme("selected" if self.focused else "selected_unfocused")
            elif(index == self.hovered):
                pass#s = self.theme("button_hover")
            c.text(0, row, pad_right(" " + str(item), c.width), s)
    def content_size(self):
        width = max([text_width(str(item)) for item in self.items] + [6])
        return width + 2, max(1, min(len(self.items), 10))


class Tree(Widget):
    """A list of items that fold open to show the items inside them.

    nodes is a dict of label -> children, where children is another dict, a list,
    None for a leaf, or a function returning the children (called when first opened):
        Tree({"src": {"main.py": None, "util.py": None}, "docs": ["intro.md"]})

    A node is identified by its path, a tuple of labels: ("src", "main.py")."""
    nodes: Any = field(default_factory=dict, kw_only=False)
    selected: Optional[tuple] = None # path of the highlighted node
    select_callback: Optional[Callable[[tuple], Any]] = field(default=None, alias="on_select")
    border = True
    focusable = True
    def init(self):
        self.expanded = set() # paths of open nodes
        self.scroll = 0
        self._loaded = {} # path -> children, for nodes given as functions
        self._follow = True # scroll to the selection on the next draw
    def on_select(self, callback: Callable[[tuple], Any]): # called with the path on Enter or a click
        self.select_callback = callback

    def _children(self, path, value):
        """A node's children as (label, value) pairs."""
        if(callable(value)):
            if(path not in self._loaded): self._loaded[path] = value()
            value = self._loaded[path]
        if(value is None): return []
        if(isinstance(value, dict)): return list(value.items())
        out = []
        for item in value:
            if(isinstance(item, dict)): out.extend(item.items())
            else: out.append((item, None))
        return out
    def _rows(self):
        """The visible rows as (path, depth, is_branch)."""
        rows = []
        def walk(children, parent):
            for label, value in children:
                path = parent + (str(label),)
                rows.append((path, len(parent), value is not None))
                if(value is not None and path in self.expanded):
                    walk(self._children(path, value), path)
        walk(self._children((), self.nodes), ())
        return rows
    def _index(self, rows):
        return next((i for i, row in enumerate(rows) if row[0] == self.selected), 0)

    def expand(self, path=None):
        """Open a node (the selected one by default)."""
        self.expanded.add(tuple(path or self.selected or ()))
        self.refresh()
    def collapse(self, path=None):
        self.expanded.discard(tuple(path or self.selected or ()))
        self.refresh()
    def toggle(self, path=None):
        path = tuple(path or self.selected or ())
        (self.collapse if path in self.expanded else self.expand)(path)
    def expand_all(self):
        """Open every node, except ones given as functions that haven't been opened yet."""
        def walk(children, parent):
            for label, value in children:
                path = parent + (str(label),)
                if(value is not None and (not callable(value) or path in self._loaded)):
                    self.expanded.add(path)
                    walk(self._children(path, value), path)
        walk(self._children((), self.nodes), ())
        self.refresh()
    def collapse_all(self):
        self.expanded.clear()
        self.refresh()
    def reload(self, path=None):
        """Forget the cached children of function nodes (all of them by default),
        so they're asked again. Use after the data behind them changes."""
        if(path is None): self._loaded.clear()
        else: self._loaded.pop(tuple(path), None)
        self.refresh()

    def _choose(self):
        if(self.selected is not None): _call(self.select_callback, self.selected)
    def _move_to(self, path):
        self._follow = True
        self.selected = path

    def on_input(self, input):
        rows = self._rows()
        if(not rows): return
        index = self._index(rows)
        path, depth, branch = rows[index]
        if(input.type == "key"):
            key = input.details["key"]
            moves = {"up": -1, "down": 1, "page_up": -self.height, "page_down": self.height,
                     "home": -len(rows), "end": len(rows)}
            if(key in moves):
                self._move_to(rows[max(0, min(len(rows) - 1, index + moves[key]))][0])
            elif(key == "right" and branch):
                if(path not in self.expanded): self.expand(path)
                elif(index + 1 < len(rows) and rows[index + 1][1] > depth): self._move_to(rows[index + 1][0])
            elif(key == "left"):
                if(path in self.expanded): self.collapse(path)
                elif(depth > 0): self._move_to(path[:-1]) # up to the parent
            elif(key in ("enter", "space")):
                if(self.selected is None): self.selected = path
                if(branch): self.toggle(path)
                self._choose()
        elif(input.type == "mouse_down" and self.mouse_over()):
            y = self.mouse_pos()[1]
            if(self.scroll + y >= len(rows)): return
            path, depth, branch = rows[self.scroll + y]
            self.selected = path
            if(branch): self.toggle(path)
            self._choose()
        elif(input.type == "mouse_scroll" and self.mouse_over()):
            step = -1 if input.details["direction"] == "up" else 1
            self.scroll = max(0, min(len(rows) - self.height, self.scroll + step))

    def draw(self, c):
        rows = self._rows()
        index = self._index(rows)
        if(self._follow): # keep the selection in view
            if(index < self.scroll): self._set_scroll(index)
            if(index >= self.scroll + c.height): self._set_scroll(index - c.height + 1)
            self._follow = False
        self._set_scroll(max(0, min(self.scroll, len(rows) - c.height)))
        for row, (path, depth, branch) in enumerate(rows[self.scroll:self.scroll + c.height]):
            s = ""
            if(self.scroll + row == index):
                s = self.theme("selected" if self.focused else "selected_unfocused")
            arrow = ("▾ " if path in self.expanded else "▸ ") if branch else "  "
            c.text(0, row, pad_right(fit(" " + "  " * depth + arrow + path[-1], c.width), c.width), s)
    def _set_scroll(self, value):
        object.__setattr__(self, "scroll", value) # no redraw, we're already drawing
    def content_size(self):
        rows = self._rows()
        width = max([text_width(path[-1]) + 2 * depth for path, depth, _ in rows] + [6])
        return width + 4, max(1, min(len(rows), 10))


class Table(Widget):
    columns: list = field(default_factory=list, kw_only=False) # header names
    rows: list = field(default_factory=list)                   # lists of values
    border = True
    def init(self):
        self.scroll = 0
    def on_input(self, input):
        if(input.type == "mouse_scroll" and self.mouse_over()):
            step = -1 if input.details["direction"] == "up" else 1
            self.scroll = max(0, min(max(0, len(self.rows) - (self.height - 1)), self.scroll + step))
    def draw(self, c):
        cells = [[str(v) for v in row] for row in self.rows]
        count = len(self.columns)
        if(not count): return
        widths = [max([text_width(self.columns[i])] + [text_width(r[i]) for r in cells if i < len(r)]) for i in range(count)]
        # Shrink the widest columns until it fits, 2 spaces between columns
        while(sum(widths) + 2 * (count - 1) > c.width and max(widths) > 1):
            widths[widths.index(max(widths))] -= 1
        def line(y, values, s):
            x = 0
            for i in range(count):
                c.text(x, y, pad_right(values[i] if i < len(values) else "", widths[i]), s)
                x += widths[i] + 2
        line(0, self.columns, self.theme("header"))
        for row, values in enumerate(cells[self.scroll:self.scroll + c.height - 1]):
            line(row + 1, values, "")
    def content_size(self):
        cells = [[str(v) for v in row] for row in self.rows]
        widths = [max([text_width(str(col))] + [text_width(r[i]) for r in cells if i < len(r)])
                  for i, col in enumerate(self.columns)]
        return min(80, sum(widths) + 2 * max(0, len(widths) - 1)), min(len(self.rows) + 1, 12)
