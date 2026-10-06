from __future__ import annotations

import copy
import inspect
import re
import sys
from typing import TYPE_CHECKING, Any, Callable, Literal, Optional, TypeVar, Union
from .shorts import *
from .inputs import Input, mouse

if sys.version_info >= (3, 11):
    from typing import dataclass_transform
else:
    def dataclass_transform(**kwargs):
        return lambda cls: cls

# A size: 5 or "5" exactly, "5+" at least 5, "5-10" between, None for any size
Size = Union[int, str, None]
Align = Literal["left", "center", "right"]
W = TypeVar("W", bound="Widget")

_MISSING = object()


class _Field:
    def __init__(self, default, default_factory, kw_only, alias):
        self.default = default
        self.default_factory = default_factory
        self.kw_only = kw_only
        self.alias = alias


def field(default: Any = _MISSING, *, default_factory: Optional[Callable[[], Any]] = None,
          kw_only: bool = True, alias: Optional[str] = None) -> Any:
    """Customise a widget field:
        items: list = field(default_factory=list)       # a fresh list per widget
        text: str = field(default="", kw_only=False)     # can be passed positionally
        callback: ... = field(default=None, alias="on_click")  # constructor argument name"""
    return _Field(default, default_factory, kw_only, alias)

# Type name -> widget class, for layout strings. Filled in automatically.
WIDGET_TYPES = {}

# Styles used by the built-in widgets. Pass View(theme={...}) to change any of them.
DEFAULT_THEME = {
    "border": "",
    "border_focus": style(fg="cyan", bold=True),
    "title": style(bold=True),
    "text": "",
    "dim": style(fg="bright_black"),
    "error": style(fg="red"),
    "button": "",
    "button_hover": style(reverse=True),
    "button_focus": style(fg="cyan", bold=True),
    "cursor": style(reverse=True),
    "selected": style(fg="black", bg="cyan"),
    "selected_unfocused": style(reverse=True),
    "progress": style(fg="green"),
    "progress_empty": style(fg="bright_black"),
    "header": style(bold=True, underline=True),
    "on": style(fg="black", bg="green", bold=True),
    "off": style(fg="bright_black", reverse=True),
    "slider": style(fg="cyan"),
    "slider_empty": style(fg="bright_black"),
    "slider_focus": style(fg="cyan", bold=True, reverse=True),
}

# Changing these means the layout has to be worked out again
LAYOUT_ATTRS = {"preferred_width", "preferred_height", "border"}
# Changing these means the borders have to be drawn again
BORDER_ATTRS = {"title"}
# Set by the view, so changing them shouldn't trigger a redraw
POSITION_ATTRS = {"x", "y", "width", "height", "name", "view"}


@dataclass_transform(kw_only_default=True, field_specifiers=(field,))
class _FieldWidget:
    """Marks widgets as dataclass-like for editors: annotated class attributes
    become constructor arguments, with autocomplete and type checking."""


class Widget(_FieldWidget):
    # Fields: annotated attributes become constructor arguments (keyword-only
    # unless field(kw_only=False)). Subclasses can change a default by just
    # assigning it, e.g. `border = True`.
    preferred_width: Size = None  # sizes of the content, not counting the border
    preferred_height: Size = None
    border: bool = False          # drawn by the view; {b} / {nb} in the layout overrides this
    title: Optional[str] = None   # shown in the border, defaults to the widget's name

    # Class settings (not constructor arguments)
    type_name = None      # name used in layouts, defaults to the class name in snake_case
    focusable = False     # can be focused with Tab or a click, and then gets key presses
    captures_text = False # when focused, typed characters go to it before key bindings

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        _collect_fields(cls)
        name = cls.__dict__.get("type_name") or re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__).lower()
        WIDGET_TYPES[name] = cls

    def __init__(self, *args, **kwargs):
        self._ready = False # attribute changes only redraw once set up
        self._dirty = True
        self._canvas: Optional[Canvas] = None # last drawn content
        # Where the widget is on screen. The view sets these from the layout;
        # set them in init() for widgets added with view.add()
        self.x = 0
        self.y = 0
        self.width = 0
        self.height = 0
        self.name: Optional[str] = None # set by the view for layout widgets
        self.view: Any = None # the View showing this widget
        self._popup: Any = None # the Popup this widget is in, if any
        for name, info in type(self)._fields.items():
            value = info.default_factory() if info.default_factory else getattr(type(self), name, None)
            object.__setattr__(self, name, value)
        self.init()
        self._apply(args, kwargs)
        self._ready = True

    def _apply(self, args, kwargs):
        """Set attributes from constructor-style arguments."""
        fields = type(self)._fields
        positional = [name for name, info in fields.items() if not info.kw_only]
        if len(args) > len(positional):
            raise TypeError(f"{type(self).__name__}() takes {len(positional)} positional "
                            f"argument{'s' if len(positional) != 1 else ''} ({', '.join(positional) or 'none'}), "
                            f"got {len(args)}")
        names = {(info.alias or name): name for name, info in fields.items()}
        values = dict(zip(positional, args))
        for key, value in kwargs.items():
            if key in names:
                name = names[key]
            elif not key.startswith("_") and key in self.__dict__:
                name = key # widgets that set attributes in init() instead of declaring fields
            else:
                raise TypeError(f"{type(self).__name__}() got an unexpected argument '{key}' "
                                f"(accepts: {', '.join(sorted(names))})")
            if name in values:
                raise TypeError(f"{type(self).__name__}() got '{key}' twice")
            values[name] = value
        for name, value in values.items():
            setattr(self, name, value)

    def set(self: W, **kwargs) -> W:
        """Change several attributes at once, redrawing once: label.set(text="Hi", align="center")"""
        object.__setattr__(self, "_ready", False)
        try:
            self._apply((), kwargs)
        finally:
            object.__setattr__(self, "_ready", True)
        if self.view and any(key in LAYOUT_ATTRS for key in kwargs):
            self.view.relayout()
        elif self.view and any(key in BORDER_ATTRS for key in kwargs):
            self.view._redraw_borders()
        self.refresh()
        return self

    def copy(self: W) -> W:
        """A separate copy of this widget, not attached to any view. Lists and
        dicts are copied so the two don't share items; callbacks are shared."""
        new = copy.copy(self)
        for key, value in vars(new).items():
            if isinstance(value, (list, dict, set)):
                new.__dict__[key] = copy.copy(value)
        new.__dict__.update(view=None, name=None, _popup=None, _canvas=None, _dirty=True)
        return new

    if not TYPE_CHECKING:
        # Hidden from type checkers: a __setattr__ makes them accept any attribute
        # name, and we want typos like `label.txt = ...` flagged.
        def __setattr__(self, key, value):
            # Changing any public attribute redraws the widget, so `button.text = "Go"` just works.
            # Mutating a list in place (self.items.append) doesn't, call self.refresh() for that.
            object.__setattr__(self, key, value)
            if key.startswith("_") or not self.__dict__.get("_ready") or key in POSITION_ATTRS:
                return
            if key in LAYOUT_ATTRS:
                if self.view: self.view.relayout()
            elif key in BORDER_ATTRS:
                if self.view: self.view._redraw_borders()
            else:
                self.refresh()

    @property
    def focused(self):
        return self.view is not None and self.view.focused is self

    def theme(self, key):
        """A style from the view's theme."""
        return (self.view.theme if self.view else DEFAULT_THEME).get(key, "")

    def refresh(self):
        """Redraw on the next frame. Safe to call from any thread."""
        self._dirty = True
        if self.view: self.view._wake()

    def mouse_pos(self):
        """Mouse position relative to this widget's top-left corner."""
        return mouse.x - self.x, mouse.y - self.y

    def mouse_over(self):
        """True if the mouse is inside this widget (and not on a popup covering it)."""
        x, y = self.mouse_pos()
        if not (0 <= x < self.width and 0 <= y < self.height): return False
        return self.view is None or self.view._layer_at(mouse.x, mouse.y) is self._popup

    def content_size(self) -> tuple[Optional[int], Optional[int]]:
        """The size the content would like (width, height), None if it doesn't
        matter. Popups use it to size themselves."""
        return None, None

    # --- Override these ---
    def init(self): pass             # set up attributes; the size isn't known yet
    def draw(self, c: Canvas): pass  # draw into c, which is exactly width x height
    def on_input(self, input: Input): pass # key inputs only arrive while focused
    def on_resize(self): pass        # called after x, y, width, height change
    def on_focus(self): pass
    def on_blur(self): pass


def _annotations(cls):
    try:
        return inspect.get_annotations(cls)
    except Exception:
        return cls.__dict__.get("__annotations__", {})


def _collect_fields(cls):
    """Work out a widget class's fields from its annotations (and its bases')."""
    own = {}
    for name, hint in _annotations(cls).items():
        if name.startswith("_") or "ClassVar" in str(hint):
            continue
        value = cls.__dict__.get(name, _MISSING)
        info = value if isinstance(value, _Field) else _Field(value, None, True, None)
        own[name] = info
        # Leave a plain default on the class, so `getattr(cls, name)` works and
        # subclasses can override it by assignment
        if info.default is not _MISSING:
            setattr(cls, name, info.default)
        elif name in cls.__dict__:
            delattr(cls, name)
    cls._own_fields = own
    fields = {}
    for klass in reversed(cls.__mro__):
        fields.update(klass.__dict__.get("_own_fields", {}))
    cls._fields = fields

_collect_fields(Widget)


def _call(callback, *args):
    if callback: callback(*args)


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


class Button(Widget):
    text: str = field(default="Button", kw_only=False)
    callback: Optional[Callable[[], Any]] = field(default=None, alias="on_click")
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
        c.text(0, mid, "[" + pad_center(self.text, c.width - 2) + "]", s)
    def content_size(self):
        return text_width(self.text) + 4, 1


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
        c.text(0, c.height // 2, fit(("[x] " if self.checked else "[ ] ") + self.text, c.width), s)
    def content_size(self):
        return text_width(self.text) + 5, 1 # one space after, so neighbours don't touch


class Toggle(Checkbox):
    """An on/off switch. Same as Checkbox, drawn differently."""
    def draw(self, c):
        mid = c.height // 2
        x = c.text(0, mid, " ON  " if self.checked else " OFF ", self.theme("on" if self.checked else "off"))
        c.text(x + 1, mid, fit(self.text, c.width - x - 1), self.theme("button_focus") if self.focused else "")
    def content_size(self):
        return text_width(self.text) + 7, 1


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


class Stdout(Widget):
    """Shows everything printed (and stderr, in red). Scroll with the mouse wheel."""
    max_lines: int = 500
    border = True
    preferred_width = "10+"
    preferred_height = "3+"
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
