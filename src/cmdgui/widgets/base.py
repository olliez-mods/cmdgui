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
BorderStyle = Literal["single", "rounded", "heavy", "double", "ascii"]
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
    "selection": style(fg="black", bg="bright_blue"), # selected text in a text box
    "selected": style(fg="black", bg="cyan"),
    "selected_unfocused": style(reverse=True),
    "hover": style(bg="bright_black"),          # the menu item under the mouse
    "tab": "",                                 # a tab on a Tabs bar
    "tab_active": style(bold=True),            # the shown tab
    "progress": style(fg="green"),
    "progress_empty": style(fg="bright_black"),
    "header": style(bold=True, underline=True),
    "on": style(fg="black", bg="green", bold=True),
    "off": style(fg="bright_black", reverse=True),
    "disabled": style(fg="bright_black"), # replaces every style in a disabled widget
    "slider": style(fg="cyan"),
    "slider_empty": style(fg="bright_black"),
    "slider_focus": style(fg="cyan", bold=True, reverse=True),
    "divider_hover": style(fg="yellow", bold=True), # a draggable line under the mouse, or being dragged
    "today": style(bold=True, underline=True), # today's date in a Calendar
    "log_debug": style(fg="bright_black"),     # the level names in a Log
    "log_info": style(fg="cyan"),
    "log_warning": style(fg="yellow", bold=True),
    "log_error": style(fg="red", bold=True),
    "log_critical": style(fg="white", bg="red", bold=True),
    "match": style(fg="black", bg="yellow"),   # text matching a Log's search
    "toast_info": style(fg="cyan"),            # the border and icon of a view.notify() message
    "toast_ok": style(fg="green"),
    "toast_warning": style(fg="yellow", bold=True),
    "toast_error": style(fg="red", bold=True),
    "hint_key": style(fg="cyan", bold=True),   # a key in a KeyHints footer
    "hint": "",                                # what the key does
}

# Changing these means the layout has to be worked out again
LAYOUT_ATTRS = {"preferred_width", "preferred_height", "border", "visible"}
# Changing these means the borders have to be drawn again
BORDER_ATTRS = {"title", "border_style"}
# Set by the view, so changing them shouldn't trigger a redraw
POSITION_ATTRS = {"x", "y", "width", "height", "view"}


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
    border: bool = False          # drawn by the view; {+b} / {-b} in the layout sets it
    border_style: Optional[BorderStyle] = None # "single", "rounded", "heavy", "double", "ascii"; None for the view's
    title: Optional[str] = None   # shown in the border, defaults to the widget's name
    enabled: bool = True          # False greys it out and ignores the mouse and keyboard
    visible: bool = True          # False hides it, and the layout closes up the space it took
    tab_stop: bool = True         # False: Tab skips it (a click can still focus it)

    # Class settings (not constructor arguments)
    type_name = None      # name used in layouts, defaults to the class name in snake_case
    focusable = False     # can be focused with Tab or a click, and then gets key presses
    captures_text = False # when focused, typed characters go to it before key bindings

    _auto_type = True     # usable in layout strings by its class name; panels set this to False

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        _collect_fields(cls)
        name = cls.__dict__.get("type_name")
        if name is None and cls._auto_type:
            name = re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__).lower()
        if name: WIDGET_TYPES[name] = cls

    def __init__(self, *args, **kwargs):
        self._setup()
        self.init()
        self._apply(args, kwargs)
        self._ready = True

    def _setup(self):
        """The state every widget has, and the fields' defaults."""
        self._ready = False # attribute changes only redraw once set up
        self._dirty = True
        self._canvas: Optional[Canvas] = None # last drawn content
        # Where the widget is on screen. The view sets these from the layout;
        # set them in init() for widgets added with view.add()
        self.x = 0
        self.y = 0
        self.width = 0
        self.height = 0
        self._name: Optional[str] = None # its name in the layout (underscored, so a panel can hold a widget called name)
        self.view: Any = None # the View showing this widget
        self._popup: Any = None # the Popup this widget is in, if any (even inside a tab of it)
        self._group: Any = None # the View or Panel (or Tabs, or Popup) it's in
        self._framed = False    # whether the layout gave it a border
        for name, info in type(self)._fields.items():
            value = info.default_factory() if info.default_factory else getattr(type(self), name, None)
            object.__setattr__(self, name, value)

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
        self._drop_focus()
        return self

    def copy(self: W) -> W:
        """A separate copy of this widget, not attached to any view. Lists and
        dicts are copied so the two don't share items; callbacks are shared."""
        new = copy.copy(self)
        for key, value in vars(new).items():
            if isinstance(value, (list, dict, set)):
                new.__dict__[key] = copy.copy(value)
        new.__dict__.update(view=None, _name=None, _popup=None, _group=None, _framed=False,
                            _canvas=None, _dirty=True)
        return new

    if not TYPE_CHECKING:
        # Hidden from type checkers: a __setattr__ makes them accept any attribute
        # name, and we want typos like `label.txt = ...` flagged.
        def __setattr__(self, key, value):
            # Changing any public attribute redraws the widget, so `button.text = "Go"` just works.
            # Mutating a list in place (self.items.append) doesn't, call self.refresh() for that.
            if key == "border_style" and value not in (None, *BORDERS):
                raise ValueError(f"unknown border style {value!r} (use {', '.join(BORDERS)})")
            object.__setattr__(self, key, value)
            if key.startswith("_") or not self.__dict__.get("_ready") or key in POSITION_ATTRS:
                return
            if key in LAYOUT_ATTRS:
                if self.view: self.view.relayout()
            elif key in BORDER_ATTRS:
                if self.view: self.view._redraw_borders()
            else:
                self.refresh()
            if key in ("enabled", "visible"): self._drop_focus()

    def _drop_focus(self):
        """Hidden or disabled: give up focus, if this or a widget inside it has it."""
        if self.enabled and self.visible or self.view is None: return
        focused = self.view.focused
        if focused is self or (focused is not None and self in _groups(focused)): self.view.focus(None)

    @property
    def focused(self):
        return self.view is not None and self.view.focused is self

    @property
    def can_focus(self):
        """True if a click (or Tab, with tab_stop) can focus this widget right now."""
        return self.focusable and self._usable and self.visible

    @property
    def _usable(self):
        """Enabled, and so is everything it's inside: a disabled panel disables its widgets."""
        return self.enabled and all(getattr(group, "enabled", True) for group in _groups(self))

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

    # --- Widgets inside widgets ---
    # Panel (and so Tabs and Popup) override these. The view uses them to find, place
    # and draw the widgets inside.

    def _inside(self, hidden=False) -> list:
        """The widgets inside this one that are shown, or with hidden=True all of them
        (like the widgets on tabs that aren't shown)."""
        return []

    def _arrange_children(self) -> None:
        """Place the widgets inside, after this widget's own rectangle is set."""

    def _needed_size(self, fit_content, bordered):
        """The smallest content (width, height) the widgets inside need, or None
        for either. fit_content: size them to their content (in popups)."""
        return None, None

    def _draw_area(self):
        """The part of the widget it draws itself: (x, y, width, height) relative to
        its top-left corner. Panels draw nothing, so the widgets and borders inside show."""
        return 0, 0, self.width, self.height

    def _border_shapes(self, frame):
        """What to draw for this widget's border, given the frame the layout made:
        ({key: rectangle}, {(x, y): directions to leave out}). The frame by default;
        Tabs draws a box around the active tab instead."""
        return {self: frame}, {}

    def _border_marks(self) -> dict:
        """Changes to the border lines once they're drawn: {(x, y): (char, style)} in
        screen cells. char replaces a plain straight line there (None keeps it); junctions
        are kept, and only restyled."""
        return {}

    def key_hints(self) -> list:
        """The keys this widget uses while it's focused, for a KeyHints footer:
        [("up/down", "Move"), ("enter", "Select")]. Join keys with / to show them as one."""
        return []

    def _child_key_hints(self) -> list:
        """Keys that work while a widget inside this one is focused (see _child_key)."""
        return []

    def _claims_key(self, key) -> bool:
        """True to get this key while focused before key bindings and Tab do, e.g. a text
        box copying its selection with Ctrl+C (which otherwise quits)."""
        return False

    def _child_key(self, key) -> bool:
        """A key pressed while a widget inside this one is focused. Return True
        if it was used (e.g. Ctrl+Page Down to switch tabs)."""
        return False

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
        value = cls.__dict__.get(name, _MISSING)
        if name.startswith("_") or "ClassVar" in str(hint) or isinstance(value, Widget):
            continue # files: Tree = Tree() in a panel is a widget in it, not a setting
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


def _groups(widget):
    """What a widget is inside, innermost first: its panel (or Tabs), what that's in,
    and so on up to the view or popup."""
    group = widget._group
    while group is not None:
        yield group
        group = getattr(group, "_group", None) # a view has none


def _call(callback, *args):
    if callback: callback(*args)
