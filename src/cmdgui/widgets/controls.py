from __future__ import annotations

from typing import Any, Callable, Optional
from ..shorts import *
from ..inputs import mouse
from .base import Widget, field, _call
from .text import _styled

class Button(Widget):
    text: str = field(default="Button", kw_only=False)
    callback: Optional[Callable[[], Any]] = field(default=None, alias="on_click")
    markup: bool = True # read [style]...[/] in the text
    preferred_width = "5+"
    preferred_height = 1
    focusable = True
    def init(self):
        self.hovered = False
    def on_click(self, callback: Callable[[], Any]):
        self.callback = callback
    def on_input(self, input):
        if(input.type == "key"):
            if(input.details["key"] in ("enter", "space")): _call(self.callback)
            return
        if(not input.type.startswith("mouse")): return

        if(self.mouse_over() != self.hovered):
            self.hovered = self.mouse_over()

        if(input.type == "mouse_down" and self.hovered):
            _call(self.callback)

    def draw(self, c):
        mid = c.height // 2 # vertically centred
        s = self.theme("button_hover" if self.hovered else "button_focus" if self.focused else "button")
        c.put(0, mid, "[", s)
        c.styled(1, mid, *_styled(self, self.text, s), s, max(0, c.width - 2), "center")
        c.put(c.width - 1, mid, "]", s)
    def content_size(self):
        return text_width(_styled(self, self.text, "")[0]) + 4, 1


class Select(Widget):
    """A dropdown: shows the chosen option, and opens the list of options when clicked
    (or Enter/Space when focused). Up/down change the choice without opening it."""
    options: list = field(default_factory=list, kw_only=False)
    selected: Optional[int] = 0 # None for nothing chosen yet
    placeholder: str = "choose…" # shown when nothing is chosen
    change_callback: Optional[Callable[[int, Any], Any]] = field(default=None, alias="on_change")
    preferred_width = "5+"
    preferred_height = 1
    focusable = True
    def init(self):
        self.hovered = False
        self.dropdown = None # the open Popup, if any
    def on_change(self, callback: Callable[[int, Any], Any]): # called with (index, option)
        self.change_callback = callback
    @property
    def value(self):
        """The chosen option, or None."""
        if(self.selected is None or not 0 <= self.selected < len(self.options)): return None
        return self.options[self.selected]
    @property
    def is_open(self):
        return self.dropdown is not None and self.dropdown.is_open

    def select(self, index):
        """Choose an option by index, calling on_change if it's a different one."""
        if(not self.options): return
        index = max(0, min(len(self.options) - 1, index))
        if(index != self.selected):
            self.selected = index
            _call(self.change_callback, index, self.options[index])
    def open(self):
        """Show the list of options below the widget (above if there's no room)."""
        if(self.view is None or not self.options or self.is_open): return
        from ..view import Popup # here, because view.py imports the widgets
        from .lists import Menu
        menu = Menu(list(self.options), selected=self.selected or 0, border=False, on_select=self._picked)
        width = max(self.width, menu.content_size()[0] + 2) # at least as wide as the widget
        self.dropdown = Popup(menu, close_on_outside_click=True, width=width,
                              on_close=lambda: self.refresh())
        self.view.show(self.dropdown, below=self)
    def close(self):
        if(self.dropdown): self.dropdown.close()
    def _picked(self, index, option):
        self.close()
        self.select(index)

    def on_input(self, input):
        if(input.type == "key"):
            key = input.details["key"]
            if(key in ("enter", "space", "alt+down")): self.open()
            elif(key == "up"): self.select((self.selected or 0) - 1)
            elif(key == "down"): self.select(0 if self.selected is None else self.selected + 1)
            elif(key == "home"): self.select(0)
            elif(key == "end"): self.select(len(self.options) - 1)
            return
        if(not input.type.startswith("mouse")): return
        if(self.mouse_over() != self.hovered):
            self.hovered = self.mouse_over()
        if(input.type == "mouse_down" and self.hovered):
            self.open()

    def draw(self, c):
        mid = c.height // 2
        s = self.theme("button_hover" if self.hovered else "button_focus" if self.focused or self.is_open else "button")
        label = self.placeholder if self.value is None else str(self.value)
        inner = max(0, c.width - 5) # room between "[ " and " ▾]"
        x = c.text(0, mid, "[ ", s)
        c.text(x, mid, pad_right(fit(label, inner), inner), self.theme("dim") if self.value is None else s)
        c.text(x + inner, mid, " ▾]", s)
    def content_size(self):
        longest = max([text_width(str(option)) for option in self.options] + [text_width(self.placeholder)])
        return longest + 5, 1


class ProgressBar(Widget):
    value: float = field(default=0.0, kw_only=False) # 0 to 1
    show_percent: bool = True
    preferred_height = 1
    def draw(self, c):
        value = max(0.0, min(1.0, float(self.value)))
        label = f" {round(value * 100):>3}%" if self.show_percent else ""
        bar = max(0, c.width - len(label))
        filled = round(value * bar)
        mid = c.height // 2
        c.text(0, mid, "█" * filled, self.theme("progress"))
        c.text(filled, mid, "░" * (bar - filled), self.theme("progress_empty"))
        c.text(bar, mid, label)
    def content_size(self):
        return 20, 1


class Slider(Widget):
    """Pick a number by dragging, clicking, or the arrow keys when focused."""
    value: float = field(default=0.0, kw_only=False)
    min: float = 0.0
    max: float = 1.0
    step: Optional[float] = None # snap to multiples of this; None is smooth (arrows move 1/20th)
    show_value: bool = True
    change_callback: Optional[Callable[[float], Any]] = field(default=None, alias="on_change")
    preferred_width = "5+"
    preferred_height = 1
    focusable = True
    def init(self):
        self.dragging = False
    def on_change(self, callback: Callable[[float], Any]): # called with the value when the user changes it
        self.change_callback = callback

    def _label(self, value):
        whole = all(float(v).is_integer() for v in (self.min, self.max, self.step or 0.5))
        return f" {round(value)}" if whole else f" {value:.2f}"
    def _track_width(self, width):
        if(not self.show_value): return max(1, width)
        # Room for the longest label, so the track doesn't change length while dragging
        label = max(len(self._label(v)) for v in (self.min, self.max, self.value))
        return max(1, width - label)
    def _set(self, value):
        """Clamp, snap to the step, and tell on_change if it moved."""
        low, high = sorted((self.min, self.max))
        if(self.step):
            value = self.min + round((value - self.min) / self.step) * self.step
            if(isinstance(self.step, int) and isinstance(self.min, int)): value = int(value)
            else: value = round(value, 10) # tidy up 0.30000000000000004
        value = max(low, min(high, value))
        if(value != self.value):
            self.value = value
            _call(self.change_callback, value)
    def _set_from_mouse(self):
        track = self._track_width(self.width)
        x = max(0, min(track - 1, self.mouse_pos()[0]))
        self._set(self.min + (self.max - self.min) * (x / max(1, track - 1)))

    def on_input(self, input):
        if(input.type == "key"):
            key = input.details["key"]
            step = self.step or (self.max - self.min) / 20
            moves = {"left": -step, "down": -step, "right": step, "up": step,
                     "page_down": -step * 5, "page_up": step * 5}
            if(key in moves): self._set(self.value + moves[key])
            elif(key == "home"): self._set(self.min)
            elif(key == "end"): self._set(self.max)
        elif(input.type == "mouse_down" and input.details["button"] == 0 and self.mouse_over()):
            self.dragging = True
            self._set_from_mouse()
        elif(input.type == "mouse_move" and self.dragging and mouse.is_down(0)):
            self._set_from_mouse() # keeps following the mouse outside the widget
        elif(input.type in ("mouse_up", "mouse_move") and self.dragging):
            self.dragging = False

    def draw(self, c):
        track = self._track_width(c.width)
        span = (self.max - self.min) or 1
        fraction = max(0.0, min(1.0, (self.value - self.min) / span))
        handle = round(fraction * (track - 1))
        mid = c.height // 2
        c.text(0, mid, "━" * handle, self.theme("slider"))
        c.text(handle + 1, mid, "─" * (track - handle - 1), self.theme("slider_empty"))
        c.put(handle, mid, "●", self.theme("slider_focus" if self.focused or self.dragging else "slider"))
        if(self.show_value):
            c.text(track, mid, self._label(self.value))
    def content_size(self):
        return 20, 1


class Checkbox(Widget):
    text: str = field(default="", kw_only=False)
    checked: bool = False
    markup: bool = True # read [style]...[/] in the text
    change_callback: Optional[Callable[[bool], Any]] = field(default=None, alias="on_change")
    preferred_width = "5+"
    preferred_height = 1
    focusable = True
    def on_change(self, callback: Callable[[bool], Any]): # called with True/False
        self.change_callback = callback
    def toggle(self):
        self.checked = not self.checked
        _call(self.change_callback, self.checked)
    def on_input(self, input):
        if(input.type == "mouse_down" and self.mouse_over()): self.toggle()
        if(input.type == "key" and input.details["key"] in ("enter", "space")): self.toggle()
    def draw(self, c):
        s = self.theme("button_focus") if self.focused else ""
        x = c.text(0, c.height // 2, "[x] " if self.checked else "[ ] ", s)
        c.styled(x, c.height // 2, *_styled(self, self.text, s), s, max(0, c.width - x))
    def content_size(self):
        return text_width(_styled(self, self.text, "")[0]) + 5, 1 # one space after, so neighbours don't touch


class Toggle(Checkbox):
    """An on/off switch. Same as Checkbox, drawn differently."""
    def draw(self, c):
        mid = c.height // 2
        x = c.text(0, mid, " ON  " if self.checked else " OFF ", self.theme("on" if self.checked else "off"))
        s = self.theme("button_focus") if self.focused else ""
        c.styled(x + 1, mid, *_styled(self, self.text, s), s, max(0, c.width - x - 1))
    def content_size(self):
        return text_width(_styled(self, self.text, "")[0]) + 7, 1


class RadioGroup(Widget):
    """Pick one of several options. Arrow keys or a click change the choice."""
    options: list = field(default_factory=list, kw_only=False)
    selected: int = 0
    horizontal: bool = False # options side by side instead of one per line
    change_callback: Optional[Callable[[int, Any], Any]] = field(default=None, alias="on_change")
    focusable = True
    def on_change(self, callback: Callable[[int, Any], Any]): # called with (index, option)
        self.change_callback = callback
    @property
    def value(self):
        """The selected option, or None if there are none."""
        return self.options[self.selected] if 0 <= self.selected < len(self.options) else None

    def select(self, index):
        index = max(0, min(len(self.options) - 1, index))
        if(index != self.selected and self.options):
            self.selected = index
            _call(self.change_callback, index, self.options[index])

    def _positions(self):
        """(x, y, width) of each option, relative to the widget."""
        out, x = [], 0
        for i, option in enumerate(self.options):
            width = text_width(str(option)) + 4
            out.append((x, 0, width) if self.horizontal else (0, i, width))
            x += width + 2
        return out

    def on_input(self, input):
        if(input.type == "key"):
            back, forward = ("left", "right") if self.horizontal else ("up", "down")
            key = input.details["key"]
            if(key == back): self.select(self.selected - 1)
            elif(key == forward): self.select(self.selected + 1)
            elif(key == "home"): self.select(0)
            elif(key == "end"): self.select(len(self.options) - 1)
        elif(input.type == "mouse_down" and self.mouse_over()):
            mx, my = self.mouse_pos()
            for i, (x, y, width) in enumerate(self._positions()):
                if(my == y and x <= mx < x + width):
                    self.select(i)

    def draw(self, c):
        for i, (option, (x, y, _)) in enumerate(zip(self.options, self._positions())):
            s = self.theme("button_focus") if self.focused and i == self.selected else ""
            c.text(x, y, fit(("(•) " if i == self.selected else "( ) ") + str(option), c.width - x), s)
    def content_size(self):
        positions = self._positions()
        if(not positions): return 5, 1
        if(self.horizontal):
            x, _, width = positions[-1]
            return x + width + 1, 1
        return max(width for _, _, width in positions) + 1, len(positions)
