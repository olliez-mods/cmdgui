from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Optional, Union
from ..shorts import *
from ..inputs import mouse
from .base import field, _call
from .container import Container


class Split(Container):
    """Two panels side by side (or one above the other), with a divider between them
    to drag with the mouse, or move with the arrow keys while the split is focused.

        class Files(Panel):
            layout = "tree \\n info"
            tree = Tree(...)
            info = Label()

        class Editor(Split):
            files = Files()
            text = TextArea()

        view.editor.files.tree   # typed in your editor
        view.editor.text

    Either can be a single widget instead of a panel: `log = Log()`, and then
    split.log is that widget. Or pass the two in, by name, Split(files=Files(),
    log=Log()), or in order, Split(Menu(items), Stdout()). split.first and
    split.second are the two panels (a widget given on its own is alone in one).

    position is the first panel's share: a fraction of the room (0.3), a number of
    cells (30), or a negative number of cells for the second panel (-30 keeps it 30
    wide as the terminal resizes). Dragging keeps the same kind of number."""
    position: Union[float, int] = 0.5
    vertical: bool = False # the first panel above the second, instead of side by side
    change_callback: Optional[Callable[[Union[float, int]], Any]] = field(default=None, alias="on_change")
    border = True
    focusable = True

    panel_count = (2, 2)
    positional_names = ("first", "second") # Split(Menu(), Stdout()): split.first and split.second
    widget_titles = True

    def init(self):
        self._dragging = False
        self._hovered = False # the mouse is over the divider
        self._first_size = 0 # cells for the first panel, as last arranged

    if not TYPE_CHECKING:
        def __setattr__(self, key, value):
            super().__setattr__(key, value)
            if not self.__dict__.get("_ready") or self.view is None: return
            if key == "position":
                with self.view.lock: # move the panels now, not at the next layout
                    self._arrange_children()
                self.view._redraw_borders()
            elif key == "vertical":
                self.view.relayout() # needs a different amount of room

    def on_change(self, callback: Callable[[Union[float, int]], Any]): # called with the position when the user moves the divider
        self.change_callback = callback

    @property
    def first(self):
        """The left (or top) panel."""
        return list(self.panels.values())[0]

    @property
    def second(self):
        """The right (or bottom) panel."""
        return list(self.panels.values())[1]

    # --- Sizes ---
    def _length(self):
        """Cells along the split, divider included."""
        return self.height if self.vertical else self.width

    def _limits(self):
        """The smallest and largest the first panel can be, keeping the second's minimum."""
        sizes = [panel._min_size(False, outer=self._framed) for panel in (self.first, self.second)]
        first, second = (size[1 if self.vertical else 0] for size in sizes)
        if self._framed: first, second = first - 2, second - 2 # their borders are ours and the divider
        low = max(0, first)
        return low, max(low, self._length() - 1 - max(0, second))

    def _resolve(self):
        """The first panel's size in cells, from position."""
        room = max(0, self._length() - 1)
        position = self.position
        if isinstance(position, float): size = round(position * room)
        elif position < 0: size = room + position
        else: size = position
        low, high = self._limits()
        return max(low, min(high, size))

    def _move_to(self, size):
        """Put the divider after size cells, keeping position the same kind of number."""
        low, high = self._limits()
        size = max(low, min(high, size))
        if size == self._first_size: return
        room = max(1, self._length() - 1)
        if isinstance(self.position, float): position = size / room
        elif self.position < 0: position = size - (self._length() - 1)
        else: position = size
        self.position = position
        _call(self.change_callback, position)

    # --- Container ---
    def _visible_panels(self):
        return self._panels()

    def _needed_size(self, fit_content, bordered):
        (w1, h1), (w2, h2) = (panel._min_size(fit_content, outer=bordered) for panel in (self.first, self.second))
        joined = -3 if bordered else 1 # bordered: the panels' outer edges are ours, and they share the divider
        across = -2 if bordered else 0
        if self.vertical: return max(w1, w2) + across, h1 + h2 + joined
        return w1 + w2 + joined, max(h1, h2) + across

    def _arrange_children(self):
        size = self._first_size = self._resolve()
        x, y, w, h = self.x, self.y, self.width, self.height
        first, second = self.first, self.second
        if self._framed:
            # Each panel's border is part of ours, and the divider is the line they share
            if self.vertical:
                first._arrange(x - 1, y - 1, w + 2, size + 2, outer=True)
                second._arrange(x - 1, y + size, w + 2, h - size + 1, outer=True)
            else:
                first._arrange(x - 1, y - 1, size + 2, h + 2, outer=True)
                second._arrange(x + size, y - 1, w - size + 1, h + 2, outer=True)
        elif self.vertical:
            first._arrange(x, y, w, size)
            second._arrange(x, y + size + 1, w, max(0, h - size - 1))
        else:
            first._arrange(x, y, size, h)
            second._arrange(x + size + 1, y, max(0, w - size - 1), h)

    # --- The divider ---
    # A grip (a short heavy line) in the middle shows it can be moved. It lights up under
    # the mouse and while dragged, and the grip does while the split is focused.
    def _divider_cells(self):
        """The divider's cells relative to the widget, not counting where it meets the border."""
        if self.vertical: return [(x, self._first_size) for x in range(self.width)]
        return [(self._first_size, y) for y in range(self.height)]

    @staticmethod
    def _grip(length):
        """Where the grip goes along a divider this long: 3 cells in the middle."""
        size = 3 if length >= 7 else min(1, length)
        start = (length - size) // 2
        return range(start, start + size)

    def _divider_styles(self):
        """(line style or None to leave it, grip style)."""
        if self._hovered or self._dragging:
            s = self.theme("divider_hover")
            return s, s
        return None, self.theme("border_focus" if self.focused else "border")

    def _border_marks(self):
        if not self._framed or self.view is None: return {}
        line, grip = self._divider_styles()
        cells = self._divider_cells()
        marks = {(self.x + x, self.y + y): (None, line) for x, y in cells} if line is not None else {}
        for i in self._grip(len(cells)):
            x, y = cells[i]
            marks[(self.x + x, self.y + y)] = ("━" if self.vertical else "┃", grip)
        return marks

    def _show_divider(self):
        """Redraw the divider after its look changed."""
        self.refresh()
        if self.view: self.view._redraw_borders()

    def on_focus(self): self._show_divider()
    def on_blur(self): self._show_divider()

    def _draw_area(self):
        if self._framed: return 0, 0, 0, 0 # the divider is a border line, drawn with the rest
        if self.vertical: return 0, self._first_size, self.width, min(1, self.height)
        return self._first_size, 0, min(1, self.width), self.height

    def draw(self, c):
        # Without a border, the divider is drawn here
        line, grip = self._divider_styles()
        c.fill(char="─" if self.vertical else "│", style=self.theme("border") if line is None else line)
        for i in self._grip(c.width if self.vertical else c.height):
            if self.vertical: c.put(i, 0, "━", grip)
            else: c.put(0, i, "┃", grip)

    def content_size(self):
        return self._needed_size(True, self.border)

    # --- Input ---
    def mouse_over(self):
        """True if the mouse is on the divider: the rest belongs to the panels."""
        if not super().mouse_over(): return False
        x, y = self.mouse_pos()
        return (y if self.vertical else x) == self._first_size

    def on_input(self, input):
        if(input.type == "key"):
            key = input.details["key"]
            back, forward = ("up", "down") if self.vertical else ("left", "right")
            moves = {back: -1, forward: 1, "home": -10 ** 6, "end": 10 ** 6}
            if(key in moves): self._move_to(self._first_size + moves[key])
            return
        if(not input.type.startswith("mouse")): return
        if(self.mouse_over() != self._hovered):
            self._hovered = not self._hovered
            self._show_divider()
        if(input.type == "mouse_down" and input.details["button"] == 0 and self._hovered):
            self._dragging = True
            self._show_divider()
        elif(input.type == "mouse_move" and self._dragging and mouse.is_down(0)):
            x, y = self.mouse_pos()
            self._move_to(y if self.vertical else x)
        elif(input.type in ("mouse_up", "mouse_move") and self._dragging):
            self._dragging = False
            self._show_divider()
