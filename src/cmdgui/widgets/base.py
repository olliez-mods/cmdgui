from __future__ import annotations

import copy
import inspect
import re
import sys
from typing import TYPE_CHECKING, Any, Callable, Literal, Optional, TypeVar, Union
from ..shorts import *
from ..inputs import Input, mouse

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
