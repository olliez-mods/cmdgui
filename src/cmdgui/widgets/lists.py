from __future__ import annotations

import re
from typing import Any, Callable, Optional
from ..shorts import *
from .. import clipboard
from .base import Widget, field, _call
from .text import _styled

class Menu(Widget):
    """A list to pick from with the arrow keys and Enter, or a click."""
    _wheel = True # scrolls itself
    items: list = field(default_factory=list, kw_only=False)
    selected: int = 0
    select_callback: Optional[Callable[[int, Any], Any]] = field(default=None, alias="on_select")
    markup: bool = False # read [style]...[/] in the items (off, as items are often data)
    border = True
    focusable = True
    def init(self):
        self.scroll = 0
        self.hovered = None # index of the item under the mouse
        self._follow = True # scroll to the selection on the next draw
    def on_select(self, callback: Callable[[int, Any], Any]): # called with (index, item) on Enter or click
        self.select_callback = callback
    def _choose(self):
        if(0 <= self.selected < len(self.items)):
            _call(self.select_callback, self.selected, self.items[self.selected])
    def _update_hover(self):
        index = self.scroll + self.mouse_pos()[1] if self.mouse_over() else None
        hovered = index if index is not None and index < len(self.items) else None
        if(hovered != self.hovered): self.hovered = hovered # only redraw when it changes

    def menu_context(self, x, y):
        context = super().menu_context(x, y)
        index = self.scroll + y
        found = y >= 0 and index < len(self.items)
        context.update(index=index if found else None, item=self.items[index] if found else None)
        return context
    def _menu_anchor(self):
        return 1, max(0, self.selected - self.scroll)
    def key_hints(self):
        return [("up/down", "Move"), ("enter", "Select")]

    def on_input(self, input):
        if(input.type == "key"):
            key = input.details["key"]
            moves = {"up": -1, "down": 1, "page_up": -self.height, "page_down": self.height,
                     "home": -len(self.items), "end": len(self.items)}
            if(key in moves and self.items):
                self._follow = True
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
            self._update_hover() # a different item is under the mouse now
        elif(input.type == "mouse_move"):
            self._update_hover()
    def draw(self, c):
        if(self._follow): # keep the selection in view
            if(self.selected < self.scroll): object.__setattr__(self, "scroll", self.selected)
            if(self.selected >= self.scroll + c.height): object.__setattr__(self, "scroll", self.selected - c.height + 1)
            self._follow = False
        object.__setattr__(self, "scroll", max(0, min(self.scroll, len(self.items) - c.height)))
        for row, item in enumerate(self.items[self.scroll:self.scroll + c.height]):
            index = self.scroll + row
            s = ""
            if(index == self.selected):
                s = self.theme("selected" if self.focused else "selected_unfocused")
            elif(index == self.hovered):
                s = self.theme("hover")
            x = c.text(0, row, " ", s)
            c.styled(x, row, *_styled(self, item, s), s, max(0, c.width - x))
    def content_size(self):
        width = max([text_width(_styled(self, item, "")[0]) for item in self.items] + [6])
        return width + 2, max(1, min(len(self.items), 10))


class Tree(Widget):
    """A list of items that fold open to show the items inside them.

    nodes is a dict of label -> children, where children is another dict, a list,
    None for a leaf, or a function returning the children (called when first opened):
        Tree({"src": {"main.py": None, "util.py": None}, "docs": ["intro.md"]})

    A node is identified by its path, a tuple of labels: ("src", "main.py")."""
    _wheel = True # scrolls itself
    nodes: Any = field(default_factory=dict, kw_only=False)
    selected: Optional[tuple] = None # path of the highlighted node
    select_callback: Optional[Callable[[tuple], Any]] = field(default=None, alias="on_select")
    markup: bool = False # read [style]...[/] in the labels (paths are still the labels as given)
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

    def menu_context(self, x, y):
        context = super().menu_context(x, y)
        rows = self._rows()
        row = rows[self.scroll + y] if y >= 0 and self.scroll + y < len(rows) else None
        context.update(path=row[0] if row else None, node=row[0][-1] if row else None)
        return context
    def _menu_anchor(self):
        return 1, max(0, self._index(self._rows()) - self.scroll)
    def key_hints(self):
        return [("up/down", "Move"), ("left/right", "Fold"), ("enter", "Select")]

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
            x = c.text(0, row, fit(" " + "  " * depth + arrow, c.width), s)
            c.styled(x, row, *_styled(self, path[-1], s), s, max(0, c.width - x))
    def _set_scroll(self, value):
        object.__setattr__(self, "scroll", value) # no redraw, we're already drawing
    def content_size(self):
        rows = self._rows()
        width = max([text_width(_styled(self, path[-1], "")[0]) + 2 * depth for path, depth, _ in rows] + [6])
        return width + 4, max(1, min(len(rows), 10))


_NUMBER = re.compile(r"\s*[-+]?[\d,]*\.?\d+") # a number at the start of a cell: "42", "-1.5", "1,200", "42%"

def _natural_key(value):
    """Sort numbers (and cells starting with one) by value, before text, which sorts
    ignoring case. Markup is left out."""
    if isinstance(value, (int, float)) and not isinstance(value, bool): return (0, value, "")
    text = strip_markup(str(value))
    match = _NUMBER.match(text)
    if match:
        try:
            return (0, float(match.group().replace(",", "")), text.lower())
        except ValueError:
            pass
    return (1, 0, text.lower())


class Table(Widget):
    """Rows and columns. Pick a row with the arrow keys or a click (Enter or a click
    calls on_select), and sort by clicking a column's header (again to reverse), or
    the number keys 1-9 while focused.

    Indexes are always into rows, as you gave them, whatever the sorting."""
    _wheel = True # scrolls itself
    columns: list = field(default_factory=list, kw_only=False) # header names
    rows: list = field(default_factory=list)                   # lists of values
    selected: Optional[int] = None # index in rows of the highlighted row, if any
    sort_column: Optional[int] = None # the column it's sorted by, None for the order of rows
    sort_reverse: bool = False
    sort_keys: dict = field(default_factory=dict) # column name or index -> fn(value) giving the sort key
    sortable: bool = True  # clicking a header (or 1-9) sorts
    markup: bool = False   # read [style]...[/] in the cells and headers (off, as cells are often data)
    change_callback: Optional[Callable[[int, Any], Any]] = field(default=None, alias="on_change")
    select_callback: Optional[Callable[[int, Any], Any]] = field(default=None, alias="on_select")
    sort_callback: Optional[Callable[[Optional[int], bool], Any]] = field(default=None, alias="on_sort")
    border = True
    focusable = True
    def init(self):
        self.scroll = 0
        self.hovered: Optional[int] = None # index in rows of the row under the mouse
        self._follow = True # scroll to the selection on the next draw

    def on_change(self, callback: Callable[[int, Any], Any]): # called with (index, row) when the highlighted row changes
        self.change_callback = callback
    def on_select(self, callback: Callable[[int, Any], Any]): # called with (index, row) on Enter or a click
        self.select_callback = callback
    def on_sort(self, callback: Callable[[Optional[int], bool], Any]): # called with (column, reverse) when the user sorts
        self.sort_callback = callback

    @property
    def value(self):
        """The highlighted row, or None."""
        return self.rows[self.selected] if self.selected is not None and 0 <= self.selected < len(self.rows) else None

    # --- Sorting ---
    def _column_index(self, column):
        if column is None or isinstance(column, int): return column
        return list(self.columns).index(column)

    def order(self) -> list[int]:
        """The indexes of rows, in the order they're shown."""
        indexes = list(range(len(self.rows)))
        column = self.sort_column
        if column is None or not 0 <= column < len(self.columns): return indexes
        key = self.sort_keys.get(column) or self.sort_keys.get(self.columns[column])
        def row_key(i):
            row = self.rows[i]
            value = row[column] if column < len(row) else ""
            return key(value) if key else _natural_key(value)
        return sorted(indexes, key=row_key, reverse=self.sort_reverse) # stable: ties keep their order

    def sort(self, column=None, reverse: bool = False) -> None:
        """Sort by a column (its name or index), or None for the order of rows. The
        highlighted row stays highlighted."""
        self.set(sort_column=self._column_index(column), sort_reverse=reverse)
        self._follow = True

    def _sort_by_user(self, column):
        """A header click or number key: sort by it, or reverse if it already is."""
        if not self.sortable or not 0 <= column < len(self.columns): return
        reverse = not self.sort_reverse if column == self.sort_column else False
        self.sort(column, reverse)
        _call(self.sort_callback, column, reverse)

    # --- Selection ---
    def select(self, index: Optional[int]) -> None:
        """Highlight a row by its index in rows (None for none), calling on_change if it moved."""
        if index is not None: index = max(0, min(len(self.rows) - 1, index)) if self.rows else None
        if index != self.selected:
            self.selected = index
            self._follow = True
            if index is not None: _call(self.change_callback, index, self.rows[index])

    def _move(self, step):
        order = self.order()
        if not order: return
        position = order.index(self.selected) if self.selected in order else (-1 if step > 0 else len(order))
        self.select(order[max(0, min(len(order) - 1, position + step))])

    def _choose(self):
        if self.value is not None: _call(self.select_callback, self.selected, self.value)

    # --- Layout ---
    def _layout(self, width):
        """The column widths and where each starts, shrinking the widest to fit."""
        cells = [[str(v) for v in row] for row in self.rows]
        shown = lambda text: text_width(_styled(self, text, "")[0])
        widths = [max([shown(str(self.columns[i])) + (2 if i == self.sort_column else 0)] +
                      [shown(r[i]) for r in cells if i < len(r)]) for i in range(len(self.columns))]
        # Shrink the widest columns until it fits, 2 spaces between columns
        while(sum(widths) + 2 * (len(widths) - 1) > width and max(widths, default=0) > 1):
            widths[widths.index(max(widths))] -= 1
        starts, x = [], 0
        for w in widths:
            starts.append(x)
            x += w + 2
        return cells, widths, starts

    def _row_at(self, y):
        """The index in rows of the row drawn at y (1 is the first under the header), or None."""
        order = self.order()
        position = self.scroll + y - 1
        return order[position] if y >= 1 and 0 <= position < len(order) else None

    def menu_context(self, x, y):
        context = super().menu_context(x, y)
        index = self._row_at(y)
        _, widths, starts = self._layout(self.width)
        column = next((i for i, (start, width) in enumerate(zip(starts, widths)) if start <= x < start + width + 2), None)
        context.update(index=index, row=self.rows[index] if index is not None else None, column=column)
        return context
    def _menu_anchor(self):
        order = self.order()
        position = order.index(self.selected) if self.selected in order else 0
        return 1, max(1, position - self.scroll + 1)
    def _default_menu_items(self, context):
        row = context["row"]
        return [("Copy row", lambda ctx: clipboard.copy("\t".join(str(v) for v in row)),
                 lambda ctx: 1 if row is not None else 0)]
    def key_hints(self):
        return [("up/down", "Move"), ("enter", "Select"), ("1-9", "Sort")]

    def on_input(self, input):
        if(input.type == "key"):
            key = input.details["key"]
            page = max(1, self.height - 2) # rows under the header, keeping one in view
            moves = {"up": -1, "down": 1, "page_up": -page, "page_down": page,
                     "home": -len(self.rows), "end": len(self.rows)}
            if(key in moves): self._move(moves[key])
            elif(key in ("enter", "space")): self._choose()
            elif(len(key) == 1 and key in "123456789"): self._sort_by_user(int(key) - 1)
            return
        if(not input.type.startswith("mouse")): return
        x, y = self.mouse_pos()
        over = self._row_at(y) if self.mouse_over() else None
        if(over != self.hovered): self.hovered = over
        if(input.type == "mouse_scroll" and self.mouse_over()):
            step = -1 if input.details["direction"] == "up" else 1
            self.scroll = max(0, min(max(0, len(self.rows) - (self.height - 1)), self.scroll + step))
            self.hovered = self._row_at(y)
        elif(input.type == "mouse_down" and input.details["button"] == 0 and self.mouse_over()):
            if(y == 0): # the header
                _, widths, starts = self._layout(self.width)
                column = next((i for i, (start, w) in enumerate(zip(starts, widths)) if start <= x < start + w + 2), None)
                if(column is not None): self._sort_by_user(column)
            elif(over is not None):
                self.select(over)
                self._choose()

    def draw(self, c):
        count = len(self.columns)
        if(not count): return
        cells, widths, starts = self._layout(c.width)
        order = self.order()
        body = max(0, c.height - 1)
        if(self._follow and self.selected in order): # keep the selection in view
            position = order.index(self.selected)
            if(position < self.scroll): self._set_scroll(position)
            if(position >= self.scroll + body): self._set_scroll(position - body + 1)
            self._follow = False
        self._set_scroll(max(0, min(self.scroll, len(order) - body)))
        def line(y, values, s):
            c.fill(0, y, c.width, 1, style=s)
            for i in range(count):
                c.styled(starts[i], y, *_styled(self, values[i] if i < len(values) else "", s), s, widths[i])
        header = [str(name) for name in self.columns]
        if(self.sort_column is not None and 0 <= self.sort_column < count):
            arrow = " ▼" if self.sort_reverse else " ▲"
            name = _styled(self, header[self.sort_column], "")[0]
            header[self.sort_column] = fit(escape(name) if self.markup else name, max(0, widths[self.sort_column] - 2)) + arrow
        line(0, header, self.theme("header"))
        for y, index in enumerate(order[self.scroll:self.scroll + body], start=1):
            if(index == self.selected): s = self.theme("selected" if self.focused else "selected_unfocused")
            elif(index == self.hovered): s = self.theme("hover")
            else: s = ""
            line(y, cells[index], s)
    def _set_scroll(self, value):
        object.__setattr__(self, "scroll", value) # no redraw, we're already drawing
    def content_size(self):
        _, widths, _ = self._layout(10 ** 6)
        return min(80, sum(widths) + 2 * max(0, len(widths) - 1)), min(len(self.rows) + 1, 12)
