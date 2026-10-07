from __future__ import annotations

from typing import Any, Callable, Optional
from ..shorts import *
from .base import Widget, field, _call, _groups
from ..panel import Panel, _min_size, _put

# Switch tabs from anywhere inside a Tabs widget
SWITCH_KEYS = {"ctrl+page_up": -1, "ctrl+page_down": 1}


class Tabs(Panel):
    """Several panels (or other widgets) in one place, with a bar of tab names to
    switch between them.

        class General(Panel):
            layout = "name \\n save"
            name = TextInput()
            save = Button("Save")

        class Settings(Tabs):
            general = General()
            advanced = Panel(Checkbox("debug mode"))

        class App(View):
            layout = "settings \\n log"
            settings = Settings()

        view.settings.general.name.value   # typed in your editor
        view.settings.show("advanced")

    Or pass them in: Tabs(general=General(), advanced=Advanced()). A tab can be any
    widget, so a single widget doesn't need a panel: log = Stdout(). A tab's name on
    the bar is its title, or its attribute name.
    Switch with a click on the bar, left/right while the bar is focused, or
    Ctrl+Page Up / Ctrl+Page Down from anywhere inside.

    With a border, the tabs sit above the content like a browser's, the shown one
    in a box that opens into it:
        ┌─────────┐
        │ general │ advanced
        │         └──────────────┐
        │ ...                    │"""
    current: Optional[str] = None # name of the tab being shown; the first one by default
    change_callback: Optional[Callable[[str], Any]] = field(default=None, alias="on_change")
    border = True
    focusable = True
    type_name = "tabs"

    _kind = "tabs"
    _needs = "at least one tab"

    def __init__(self, **kwargs):
        super().__init__(None, **kwargs)
        if self.current is None:
            object.__setattr__(self, "current", next(iter(self.named)))
        elif self.current not in self.named:
            raise ValueError(f"no tab named '{self.current}' (tabs: {', '.join(self.named)})")

    def init(self):
        self.hovered = None # name of the tab under the mouse
        self._bar_row = 0 # which row of the widget the tab names are on
        self._box = None  # (x, y, width, height) of the box the shown tab is in, its border if it has one
        self._focus_memory = {} # tab name -> the widget focused in it when we left

    def on_change(self, callback: Callable[[str], Any]): # called with the tab's name when it changes
        self.change_callback = callback

    @property
    def shown(self) -> Widget:
        """The tab being shown: its panel, or its widget."""
        return self.named[self.current]

    def show(self, name: str) -> None:
        """Switch to a tab by name."""
        if name not in self.named:
            raise KeyError(f"no tab named '{name}' (tabs: {', '.join(self.named)})")
        if name == self.current: return
        view, old = self.view, self.shown
        focused = view.focused if view else None
        inside = focused is not None and (focused is old or old in _groups(focused)) # focus was in the tab we're leaving
        if inside:
            self._focus_memory[self.current] = focused
        self.current = name
        self._set_frames()
        if view:
            view.refresh() # the new tab's widgets and borders
            if inside:
                # Back to where you were in this tab, or else the tab bar
                target = self._focus_memory.get(name)
                visible = list(view._walk([self.shown]))
                view.focus(target if target in visible and target.can_focus else self)
        _call(self.change_callback, name)

    def _step(self, step):
        names = list(self.named)
        self.show(names[(names.index(self.current) + step) % len(names)])

    # --- The tabs inside ---
    def _inside(self, hidden=False):
        return self.widgets if hidden else [self.shown]

    def _frame_title(self, key):
        return None # a tab's name is on the bar

    def _frame_style(self, key):
        return key.border_style or self.border_style

    def _boxed(self, tab):
        """True if a tab has a border round it: the content box, when this has a border."""
        return self._framed or tab.border

    def _needed_size(self, fit_content, bordered):
        sizes = []
        for tab in self.named.values():
            boxed = bordered or tab.border
            width, height = _min_size(tab, fit_content, boxed)
            sizes.append((width + 2, height + 2) if boxed else (width, height))
        width, height = max(w for w, _ in sizes), max(h for _, h in sizes)
        bar = self._bar_width()
        if bordered:
            # The box's sides and bottom are this widget's border, and its top the line under
            # the tab bar. One more row in case the tab box can't use the line above (see
            # _arrange_children)
            return max(width - 2, bar), height + 1
        return max(width, bar), height + 1

    def _arrange_children(self):
        # The tab box's top edge goes on the border line above this widget when nothing
        # else draws there (the usual case). Otherwise, like at the top of a popup or
        # inside other tabs, the box moves down a row inside the widget. Without a border
        # the bar is just the top row.
        self._bar_row = 0 if not self._framed or self._line_above_free() else 1
        if self._framed:
            # Share this widget's border; the box's top edge is the line under the bar
            top = self.y + self._bar_row + 1
            self._box = (self.x - 1, top, self.width + 2, self.y + self.height - top + 1)
        else:
            self._box = (self.x, self.y + 1, self.width, max(0, self.height - 1))
        x, y, w, h = self._box
        for tab in self.named.values():
            if self._boxed(tab):
                _put(tab, x + 1, y + 1, max(0, w - 2), max(0, h - 2), framed=True)
            else:
                _put(tab, x, y, w, h, framed=False)
        self._set_frames()

    def _set_frames(self):
        """The shown tab's border, drawn with the rest."""
        self.frames = {self.shown: self._box} if self._box and self._boxed(self.shown) else {}

    def _line_above_free(self):
        """True if no other border runs along the line above this widget."""
        if not self._framed: return False
        frames = self._group.frames if self._group is not None else {}
        row = self.y - 1
        for key, (fx, fy, fw, fh) in frames.items():
            if key is self: continue
            if row in (fy, fy + fh - 1) and fx + fw - 1 >= self.x and fx <= self.x + self.width - 1:
                return False
        return True

    def _draw_area(self):
        return 0, self._bar_row, self.width, min(1, self.height) # just the bar; the tabs draw the rest

    def _border_shapes(self, frame):
        """In place of a frame around everything: a box around the shown tab, open at
        the bottom into the content. The content's border is the shown tab's (see _set_frames)."""
        start, width = self._span(self.current)
        left, right = self.x + start - 1, self.x + start + width
        top = self.y + self._bar_row - 1     # the box's top edge, the row above the names
        bottom = self.y + self._bar_row + 1  # the content's top edge
        gaps = {(x, bottom): LEFT | RIGHT for x in range(left + 1, right)}
        gaps[(left, bottom)] = RIGHT
        gaps[(right, bottom)] = LEFT
        return {self: (left, top, right - left + 1, bottom - top + 1)}, gaps

    def _child_key(self, key):
        if key in SWITCH_KEYS:
            self._step(SWITCH_KEYS[key])
            return True
        return False

    def content_size(self):
        return self._needed_size(True, self.border)

    # --- The tab bar ---
    def _labels(self):
        """(name, label, start column) for each tab, as drawn on the bar. There's a
        column between tabs, where the shown tab's box has its sides."""
        out, x = [], 0
        for name, tab in self.named.items():
            label = f" {tab.title or name} "
            out.append((name, label, x))
            x += text_width(label) + 1
        return out

    def _span(self, name):
        """(start column, width) of a tab's label."""
        _, label, start = next(tab for tab in self._labels() if tab[0] == name)
        return start, text_width(label)

    def _bar_width(self):
        return sum(text_width(label) + 1 for _, label, _ in self._labels())

    def _tab_at(self, x):
        """The tab name at column x of the bar, or None."""
        for name, label, start in self._labels():
            if start <= x < start + text_width(label): return name
        return None

    def on_input(self, input):
        if(input.type == "key"):
            key = input.details["key"]
            if(key in ("left", "right")): self._step(-1 if key == "left" else 1)
            elif(key in SWITCH_KEYS): self._step(SWITCH_KEYS[key])
            elif(key == "home"): self.show(next(iter(self.named)))
            elif(key == "end"): self.show(list(self.named)[-1])
            return
        if(not input.type.startswith("mouse")): return
        x, y = self.mouse_pos()
        over = self._tab_at(x) if y == self._bar_row and self.mouse_over() else None
        if(over != self.hovered): self.hovered = over
        if(input.type == "mouse_down" and over is not None):
            self.show(over)

    def draw(self, c):
        for name, label, start in self._labels():
            if(name != self.current):
                c.text(start, 0, label, self.theme("hover" if name == self.hovered else "tab"))
            elif(self._framed):
                # Bold, in its box. The box's sides on this row are drawn here, since this
                # row is ours; the view draws the rest of it with the borders.
                c.text(start, 0, label, self.theme("tab_active"))
                edge = self.theme("border_focus" if self.focused else "border")
                c.put(start - 1, 0, "│", edge) # off the canvas for the first tab, the view has it
                c.put(start + text_width(label), 0, "│", edge)
            else:
                c.text(start, 0, label, self.theme("selected" if self.focused else "tab_active"))
