from __future__ import annotations

import _thread
import atexit
import os
import re
import signal
import sys
import threading
import time
import traceback
import copy
from typing import Any, Callable, Optional, TypeVar, Union
from .shorts import *
from .widgets import *
from .widgets import W
from .widgets.base import _containers
from .layout import parse_layout, parse_size, place, LayoutError
from . import inputs

P = TypeVar("P", bound="Popup")
G = TypeVar("G", bound="Panel")

# With keep_typing, these keys go to the popup instead of the focused text box
POPUP_KEYS = {"up", "down", "page_up", "page_down", "enter"}

# Escape codes in printed text, left out when working out how wide it is
ANSI_CODE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")

# Setup terminal
def setup(inline=False):
    write(("" if inline else ESC + "?1049h") + hide_cursor()) # the alternative screen, unless inline
    inputs.enable()

def teardown(inline=False, stderr_shown=0):
    inputs.disable()
    write(show_cursor() + ("" if inline else ESC + "?1049l")) # back to the normal screen
    # Anything written to stderr (like a traceback) and not shown yet: it was hidden on
    # the alternative screen, or written after an inline view stopped printing it
    errors = inputs.captured_stderr()[stderr_shown:]
    if errors:
        sys.stderr.write(errors)
        sys.stderr.flush()


def _draw_borders(canvas, frames, titles, focused, theme, gaps=None):
    """Draw every border at once, so shared edges are one line and meeting
    lines get the right junction (├ ┬ ┼ ...). The focused frame is drawn in
    the focus colour. titles: frame key -> title (or None). gaps: (x, y) ->
    directions to leave out there, e.g. the opening under an active tab."""
    links = {} # (x, y) -> directions that cell connects to
    def link(x, y, direction):
        links[(x, y)] = links.get((x, y), 0) | direction
    for x, y, w, h in frames.values():
        right, bottom = x + w - 1, y + h - 1
        for cx in range(x, right):
            for cy in (y, bottom):
                link(cx, cy, RIGHT)
                link(cx + 1, cy, LEFT)
        for cy in range(y, bottom):
            for cx in (x, right):
                link(cx, cy, DOWN)
                link(cx, cy + 1, UP)
    for cell, directions in (gaps or {}).items():
        if cell in links:
            links[cell] &= ~directions
            if not links[cell]: del links[cell]
    for (x, y), directions in links.items():
        canvas.put(x, y, LINE_CHARS[directions], theme["border"])

    def restyle(x, y, s):
        if 0 <= x < canvas.width and 0 <= y < canvas.height:
            canvas.styles[y][x] = s
    for name, (x, y, w, h) in frames.items():
        if name == focused:
            s = theme["border_focus"]
            for cx in range(x, x + w):
                restyle(cx, y, s)
                restyle(cx, y + h - 1, s)
            for cy in range(y, y + h):
                restyle(x, cy, s)
                restyle(x + w - 1, cy, s)
        # Title on the top edge, stopping before any junction
        title = titles.get(name)
        if not title: continue
        title_style = theme["border_focus"] if name == focused else theme["title"]
        cx = x + 2
        for char in f" {title} ":
            if cx > x + w - 3 or links.get((cx, y)) != LEFT | RIGHT: break
            cx += canvas.put(cx, y, char, title_style)


def _spec(preferred, natural):
    """A widget's size range, raised to fit its content if it has room to grow."""
    low, high = parse_size(preferred)
    if natural is not None:
        low = max(low, natural if high is None else min(natural, high))
    return f"{low}+" if high is None else f"{low}-{max(low, high)}"


class Timer:
    """A function the view calls later, once or repeatedly. Made by view.after()
    and view.every(); cancel() stops it."""
    def __init__(self, seconds: float, callback: Callable[[], Any], repeat: bool):
        self.seconds = seconds
        self.callback = callback
        self.repeat = repeat
        self._due = time.monotonic() + seconds
        self._cancelled = False
        self._finished = False # a one-off timer that has run

    @property
    def active(self) -> bool:
        """True until it's cancelled, or until a one-off timer has run."""
        return not (self._cancelled or self._finished)

    def cancel(self) -> None:
        """Stop it. Safe to call more than once, or from inside the callback."""
        self._cancelled = True


class Group():
    """Named widgets arranged by a layout string. View and Popup are both groups:
    widgets come from the layout, class attributes and keyword arguments, and
    are found with group.name, group["name"] or group.get("name", Kind)."""
    layout: Optional[str] = None # subclasses can set the layout here
    _kind = "group"              # for messages: "view" or "popup"

    def _init_group(self, layout, widgets):
        """Collect, check and create the widgets. Views run this before touching
        the terminal, so a mistake doesn't leave it in raw mode."""
        self.widgets: list[Widget] = []
        self.named: dict[str, Widget] = {} # name -> widget, for widgets from the layout
        self.frames: dict[Any, tuple[int, int, int, int]] = {} # widget (or the group itself) -> border rectangle

        # Class attributes (copied, so each instance gets its own) and keyword arguments
        provided: dict[str, Any] = {}
        for klass in reversed(type(self).__mro__):
            for name, value in vars(klass).items():
                if isinstance(value, (Widget, Popup)):
                    provided[name] = value.copy()
        for name, value in widgets.items():
            if isinstance(value, Panel) and not isinstance(value, Popup):
                raise TypeError(f"{type(self).__name__}() got a panel '{name}': panels go inside a Tabs widget")
            if not isinstance(value, (Widget, Popup)):
                raise TypeError(f"{type(self).__name__}() got an unexpected argument '{name}' "
                                f"(widgets must be Widget instances)")
            provided[name] = value
        for name in [name for name, value in provided.items() if isinstance(value, Popup)]:
            self._add_popup(name, provided.pop(name))

        self.layout = layout if layout is not None else type(self).layout or self._default_layout(provided)
        if provided and not self.layout:
            raise LayoutError(f"widgets were given ({', '.join(provided)}) but there's no layout to put them in")
        self.grid = parse_layout(self.layout, types=WIDGET_TYPES, names=provided) if self.layout else None
        if not self.grid:
            return
        unused = [name for name in provided if name not in self.grid.slots]
        if unused:
            raise LayoutError(f"widget{'s' if len(unused) > 1 else ''} {', '.join(unused)} "
                              f"{'are' if len(unused) > 1 else 'is'} not in the layout")
        for name, slot in self.grid.slots.items():
            attr = getattr(type(self), name, None)
            if name in self.__dict__ or (attr is not None and not isinstance(attr, Widget)):
                raise LayoutError(f"widget name '{name}' clashes with {self._kind}.{name}, pick another name")
            widget = provided.get(name)
            if widget is None:
                widget = WIDGET_TYPES[slot.type]()
            elif slot.type is not None and not isinstance(widget, WIDGET_TYPES[slot.type]):
                raise LayoutError(f"the layout says '{name}' is a {slot.type}, "
                                  f"but it was given a {type(widget).__name__}")
            widget.name = name
            widget._group = self
            self.widgets.append(widget)
            self.named[name] = widget
        for name, widget in self.named.items():
            self.__dict__[name] = widget # group.name finds this instance's copy, not the class attribute

    def _add_popup(self, name, popup) -> None:
        raise TypeError(f"{type(self).__name__}() got a popup '{name}', only views can hold popups")

    def _default_layout(self, provided):
        """With no layout: the widgets one above the other, in the order they're declared
        (a single widget fills the space)."""
        return "\n".join(provided) or None

    def __getitem__(self, name: str) -> Widget:
        return self.named[name]

    def get(self, name: str, kind: type[W]) -> W:
        """A widget by name, typed for your editor: view.get("heading", Label)"""
        widget = self.named[name]
        if not isinstance(widget, kind):
            raise TypeError(f"'{name}' is a {type(widget).__name__}, not a {kind.__name__}")
        return widget

    def __getattr__(self, name):
        # Only called for attributes that don't exist, so view.start finds the widget "start"
        named = self.__dict__.get("named", {})
        if name in named:
            return named[name]
        raise AttributeError(f"{self._kind} has no attribute or widget named '{name}'")

    def _place(self, width, height, fit_content=False, outer=False):
        """Work out where the widgets go in a width x height box (positions relative to it).
        fit_content: grow widgets to their content_size(); outer: leave room for a border around it all."""
        sizes, borders = {}, {}
        for name, widget in self.named.items():
            slot_border = self.grid.slots[name].border
            borders[name] = widget.border if slot_border is None else slot_border
            need_w, need_h = widget._needed_size(fit_content, borders[name]) # containers: what their panels need
            if fit_content:
                content_w, content_h = widget.content_size()
                content_w = content_w if need_w is None else need_w
                content_h = content_h if need_h is None else need_h
                sizes[name] = (_spec(widget.preferred_width, content_w), _spec(widget.preferred_height, content_h))
            elif need_w is not None or need_h is not None:
                sizes[name] = (_spec(widget.preferred_width, need_w), _spec(widget.preferred_height, need_h))
            else:
                sizes[name] = (widget.preferred_width, widget.preferred_height)
        return place(self.grid, width, height, sizes, borders, outer=outer)


class Panel(Group):
    """A layout of widgets that goes inside something else, like a tab of a Tabs widget:

        class General(Panel):
            layout = '''
                name
                save
            '''
            name = TextInput(placeholder="your name")
            save = Button("Save")

    Written just like a View subclass. Without a layout, the widgets go one above the
    other in the order they're declared, so a panel with one widget is just
    Panel(Menu(items)). Popup is a panel that floats over the view."""
    _kind = "panel"
    border: bool = False         # draw a border around the whole panel (Tabs and Popup decide this themselves)
    title: Optional[str] = None  # the tab's name in a Tabs, or the popup's border title

    def __init__(self, layout: Union[str, Widget, None] = None, *,
                 border: Optional[bool] = None, title: Optional[str] = None, **widgets: Widget):
        if border is not None: self.border = border
        if title is not None: self.title = title
        self.x = self.y = self.w = self.h = 0 # on screen, including any border
        self._container: Optional[Widget] = None # the Tabs (or other container) holding it
        self._unnamed = set() # names made up here, not shown as border titles
        if isinstance(layout, Widget):
            widgets = {"content": layout, **widgets}
            self._unnamed = {"content"}
            layout = None
        self._init_group(layout, widgets)
        if not self.grid:
            raise LayoutError(f"a {self._kind} needs a layout or at least one widget")
        self.init()

    def init(self) -> None:
        """Override to wire up widgets, e.g. self.no.on_click(self.close)."""

    def copy(self: G) -> G:
        """A separate copy with its own widgets (init() runs again for it)."""
        new = copy.copy(self)
        new.__dict__.update(widgets=[], named={}, frames={}, _container=None, **self._copy_resets())
        for name, widget in self.named.items():
            widget = widget.copy()
            widget.name = name
            widget._group = new
            new.widgets.append(widget)
            new.named[name] = widget
            new.__dict__[name] = widget
        new.init()
        return new

    def _copy_resets(self) -> dict:
        return {}

    def _min_size(self, fit_content, outer):
        """The smallest (width, height) the panel fits in."""
        placement = self._place(0, 0, fit_content=fit_content, outer=outer)
        return placement.min_width, placement.min_height

    def _arrange(self, x, y, w, h, fit_content=False, outer=False):
        """Place the widgets in the w x h box at (x, y). outer: the box's edge is a
        border line (drawn as part of the panel), shared with the widgets' borders."""
        placement = self._place(w, h, fit_content=fit_content, outer=outer)
        inner = 1 if outer else 0
        self.x, self.y, self.w, self.h = x, y, w, h
        self.frames = {self.named[name]: (x + fx, y + fy, fw, fh) for name, (fx, fy, fw, fh) in placement.frames.items()}
        if outer:
            self.frames[self] = (x, y, w, h)
        for name, (rx, ry, rw, rh) in placement.rects.items():
            widget = self.named[name]
            widget._framed = widget in self.frames
            # Clip to the inside of the box, in case it's too small
            rw = max(0, min(rw, w - inner - rx))
            rh = max(0, min(rh, h - inner - ry))
            if (widget.x, widget.y, widget.width, widget.height) != (x + rx, y + ry, rw, rh):
                widget.x, widget.y, widget.width, widget.height = x + rx, y + ry, rw, rh
                widget._dirty = True
                widget._arrange_children()
                widget.on_resize()

    def _contains(self, x, y):
        return self.x <= x < self.x + self.w and self.y <= y < self.y + self.h


class Popup(Panel):
    """A box that floats over the view, with its own layout of widgets:

        class Confirm(Popup):
            layout = '''
                message  -
                yes      no
            '''
            message = Label("Delete everything?")
            yes = Button("Yes")
            no = Button("No")

        view.show(Confirm())

    Without a layout, the widgets go one above the other in the order they're
    declared: Popup(Menu(items)) for a popup with one widget.
    Settings can be class attributes or constructor arguments."""
    _kind = "popup"
    modal: bool = True                    # block everything underneath while open
    close_on_escape: bool = True
    close_on_outside_click: bool = False
    keep_typing: bool = False             # the focused text box keeps getting typed text; arrows and Enter come here
    border: bool = True
    width: Optional[int] = None           # outer size, including the border; None to fit the content
    height: Optional[int] = None

    def __init__(self, layout: Union[str, Widget, None] = None, *,
                 modal: Optional[bool] = None, close_on_escape: Optional[bool] = None,
                 close_on_outside_click: Optional[bool] = None, keep_typing: Optional[bool] = None,
                 border: Optional[bool] = None, title: Optional[str] = None,
                 width: Optional[int] = None, height: Optional[int] = None,
                 on_close: Optional[Callable[[], Any]] = None, **widgets: Widget):
        settings = dict(modal=modal, close_on_escape=close_on_escape, keep_typing=keep_typing,
                        close_on_outside_click=close_on_outside_click, width=width, height=height)
        for key, value in settings.items():
            if value is not None: setattr(self, key, value)
        self.close_callback = on_close
        self.view: Optional[View] = None
        self._anchor: tuple[str, Any] = ("center", None)
        self._previous_focus: Optional[Widget] = None
        super().__init__(layout, border=border, title=title, **widgets)

    @property
    def is_open(self) -> bool:
        return self.view is not None

    def on_close(self, callback: Optional[Callable[[], Any]]) -> None:
        """Call callback() whenever the popup closes."""
        self.close_callback = callback

    def close(self) -> None:
        """Close the popup (does nothing if it isn't open)."""
        if self.view: self.view._close(self)

    def _copy_resets(self) -> dict:
        return {"view": None, "_previous_focus": None}


class View(Group):
    """A terminal GUI. Three ways to fill it, which can be mixed:

        View("label[heading] \n stdout")                  # types in the layout
        View("heading \n stdout", heading=Label("Hi"))    # widgets passed in

        class UI(View):                                    # a subclass: typed in your editor
            layout = "heading \n stdout"
            heading = Label("Hi")

    inline: draw in some rows under the prompt instead of taking over the whole
    screen: inline=8 for 8 rows, or True for as many as the layout needs. Printed
    text goes above it (or to a Stdout widget, if it has one), and when it closes
    the last frame stays (keep_on_exit=False clears it).

    copy_on_select: text selected with the mouse in a text box is copied straight
    away, for terminals that keep Cmd+C to themselves (all of them on macOS).
    """
    _kind = "view"

    def __init__(self, layout: Optional[str] = None, theme: Optional[dict] = None,
                 quit_key: Optional[str] = "q", inline: Union[bool, int] = False,
                 keep_on_exit: bool = True, copy_on_select: bool = False, **widgets: Widget):
        self.lock = threading.RLock() # reentrant, so widgets can call view methods while handling input
        self.running = False
        self.thread = None
        self.too_small = False
        self.focused: Optional[Widget] = None
        self.theme = {**DEFAULT_THEME, **(theme or {})}
        self.bindings = {} # key name -> function
        self.timers: list[Timer] = []
        self.size = (0, 0)
        self._base = None   # borders (or the "too small" message), widgets go on top
        self._shown = None  # what's on the terminal right now
        self._relayout = True
        self._redraw_base = True
        self._done = threading.Event()
        self._waiting = False
        self._quitting = False
        self._exit_code = 0 # 1 after a crash inside the view (e.g. in a callback)
        if inline is not False and inline is not True and (not isinstance(inline, int) or inline < 1):
            raise ValueError(f"inline should be True, False or a number of rows, got {inline!r}")
        self.inline = inline
        self.keep_on_exit = keep_on_exit
        self.copy_on_select = copy_on_select
        self._top = 0        # the screen row an inline view starts on
        self._rows = 0       # how many rows an inline view has
        self._pending = {"stdout": "", "stderr": ""} # printed text with no newline yet (inline)
        self._stderr_shown = 0 # how much of stderr an inline view has printed above itself
        self.quit_key = quit_key
        if quit_key:
            self.bindings[quit_key] = self.quit

        self.popups: list[Popup] = [] # open popups, bottom to top

        # Before touching the terminal, so a layout mistake doesn't leave it in raw mode
        self._init_group(layout, widgets)
        for widget in self._walk(self.widgets, hidden=True):
            widget.view = self
        if self.grid:
            self._place(0, 0) # checks the widgets' sizes are valid, before touching the terminal

        self._install_sigint()
        self.running = True
        atexit.register(self.stop)
        try:
            setup(bool(inline))
            if inline: self._start_inline()
            self.size = self._screen_area()
            self._render()
            self.thread = threading.Thread(target=self._input_loop, daemon=True)
            self.thread.start()
        except BaseException:
            self.stop() # restore the terminal so the error is visible
            raise

    def _add_popup(self, name, popup) -> None:
        attr = getattr(type(self), name, None)
        if attr is not None and not isinstance(attr, Popup):
            raise LayoutError(f"popup name '{name}' clashes with view.{name}, pick another name")
        self.__dict__[name] = popup # view.name finds this view's copy

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()
        return False

    # --- Widgets ---

    def add(self, widget: W) -> W:
        """Add a widget outside the layout. Set its x, y, width, height yourself."""
        with self.lock:
            self.widgets.append(widget)
            for w in self._walk([widget], hidden=True):
                w.view = self
            widget._arrange_children()
        widget.refresh()
        return widget

    def refresh(self) -> None:
        """Redraw everything on the next frame."""
        for widget in self._every_widget():
            widget._dirty = True
        self._redraw_base = True
        self._wake()

    # --- Popups ---

    def show(self, popup: P, *, at: Optional[tuple[int, int]] = None,
             below: Optional[Widget] = None, above: Optional[Widget] = None) -> P:
        """Open a popup on top of everything: in the middle of the screen, at=(x, y),
        or below= / above= a widget (flipping if there's no room). If it's already
        open, it just moves."""
        anchor = ("at", at) if at else ("below", below) if below else ("above", above) if above else ("center", None)
        with self.lock:
            popup._anchor = anchor
            if popup.view is self:
                self._place_popup(popup)
                self._redraw_base = True
            else:
                if popup.view: popup.view._close(popup)
                popup.view = self
                for widget in self._walk(popup.widgets, hidden=True):
                    widget.view = self
                    widget._popup = popup
                    widget._dirty = True
                self.popups.append(popup)
                self._place_popup(popup)
                self._redraw_base = True
                popup._previous_focus = self.focused
                if not popup.keep_typing:
                    self.focus(next((w for w in self._walk(popup.widgets) if w.can_focus), None))
        self._wake()
        return popup

    def alert(self, message: str, title: Optional[str] = None,
              on_close: Optional[Callable[[], Any]] = None) -> Popup:
        """Show a message with an OK button."""
        ok = Button("OK")
        popup = Popup("message \n ok", message=Text(message, align="center"), ok=ok,
                      title=title, on_close=on_close)
        ok.on_click(popup.close)
        return self.show(popup)

    def _close(self, popup):
        with self.lock:
            if popup not in self.popups: return
            self.popups.remove(popup)
            focused_inside = self.focused is None or self.focused._popup is popup
            for widget in self._walk(popup.widgets, hidden=True):
                widget.view = None
                widget._popup = None
            popup.view = None
            self._redraw_base = True
            if focused_inside:
                previous = popup._previous_focus
                still_there = previous is not None and (previous._popup is None or previous._popup in self.popups)
                self.focused = None # the old focus is gone, don't call its on_blur with the view detached
                self.focus(previous if still_there else None)
            popup._previous_focus = None
        self._wake()
        if popup.close_callback: popup.close_callback()

    @staticmethod
    def _walk(widgets, hidden=False):
        """The widgets, each followed by the widgets in its shown panels (all its
        panels if hidden=True), all the way down."""
        for widget in widgets:
            yield widget
            for panel in (widget._panels() if hidden else widget._visible_panels()):
                yield from View._walk(panel.widgets, hidden)

    @staticmethod
    def _layer_groups(group):
        """A view or popup, and every shown panel inside it."""
        yield group
        for widget in View._walk(group.widgets):
            yield from widget._visible_panels()

    def _all_widgets(self):
        """Every widget being shown: the layout's, and the open popups'."""
        return list(self._walk(self.widgets)) + [w for popup in self.popups for w in self._walk(popup.widgets)]

    def _every_widget(self):
        """Every widget, including ones in tabs that aren't shown."""
        return list(self._walk(self.widgets, hidden=True)) + \
               [w for popup in self.popups for w in self._walk(popup.widgets, hidden=True)]

    def _active_widgets(self):
        """Widgets that can get mouse input and focus: everything above the top modal popup."""
        for i in range(len(self.popups) - 1, -1, -1):
            if self.popups[i].modal:
                return [w for popup in self.popups[i:] for w in self._walk(popup.widgets)]
        return self._all_widgets()

    def _layer_at(self, x, y):
        """The topmost popup at (x, y), or None for the main layout."""
        for popup in reversed(self.popups):
            if popup._contains(x, y):
                return popup
        return None

    def _box(self, widget):
        """A widget's rectangle including its border."""
        frames = widget._group.frames if widget._group is not None else self.frames
        return frames.get(widget) or (widget.x, widget.y, widget.width, widget.height)

    def _place_popup(self, popup):
        """Size the popup to its content (or its width/height) and position it."""
        screen_w, screen_h = self.size
        natural = popup._place(0, 0, fit_content=True, outer=popup.border)
        w = min(popup.width or natural.min_width, screen_w)
        h = min(popup.height or natural.min_height, screen_h)

        kind, target = popup._anchor
        if kind == "at":
            x, y = target
        elif kind in ("below", "above") and target is not None:
            bx, by, bw, bh = self._box(target)
            x, below_y, above_y = bx, by + bh, by - h
            if kind == "below":
                y = below_y if below_y + h <= screen_h or above_y < 0 else above_y
            else:
                y = above_y if above_y >= 0 or below_y + h > screen_h else below_y
        else:
            x, y = (screen_w - w) // 2, (screen_h - h) // 2
        x, y = max(0, min(x, screen_w - w)), max(0, min(y, screen_h - h))

        popup._arrange(x, y, w, h, fit_content=True, outer=popup.border)

    def relayout(self) -> None:
        """Work out the layout again, e.g. after a widget's preferred size changed."""
        self._relayout = True
        self._wake()

    # --- Focus and keys ---

    def focus(self, widget: Optional[Widget]) -> None:
        """Give a widget keyboard focus (None to remove focus)."""
        with self.lock:
            old = self.focused
            if widget is old: return
            self.focused = widget
            self._redraw_base = True # the focus border changes colour
            if old:
                old.refresh()
                old.on_blur()
            if widget:
                widget.refresh()
                widget.on_focus()
        self._wake()

    def focus_next(self, step: int = 1) -> None:
        """Move focus to the next (or previous, step=-1) focusable widget."""
        with self.lock:
            focusable = [w for w in self._active_widgets() if w.can_focus]
            if not focusable: return
            if self.focused in focusable:
                index = (focusable.index(self.focused) + step) % len(focusable)
            else:
                index = 0 if step > 0 else -1
            self.focus(focusable[index])

    def on_key(self, key: str, callback: Optional[Callable[[], Any]]) -> None:
        """Call callback() when key is pressed, e.g. view.on_key("ctrl+s", save).
        Pass None to remove a binding."""
        if callback: self.bindings[key] = callback
        else: self.bindings.pop(key, None)

    # --- Timers ---

    def after(self, seconds: float, callback: Callable[[], Any]) -> Timer:
        """Call callback() once, after a delay. Runs on the view's thread, like other callbacks."""
        return self._add_timer(Timer(seconds, callback, repeat=False))

    def every(self, seconds: float, callback: Callable[[], Any]) -> Timer:
        """Call callback() every few seconds until timer.cancel() or the view closes.
        If a call runs late, the next one waits a full interval rather than catching up."""
        if seconds <= 0: raise ValueError("every() needs a positive number of seconds")
        return self._add_timer(Timer(seconds, callback, repeat=True))

    def _add_timer(self, timer):
        with self.lock:
            self.timers.append(timer)
        self._wake() # so the loop works out how long it can sleep
        return timer

    def _run_timers(self):
        now = time.monotonic()
        with self.lock:
            due = [t for t in self.timers if t.active and t._due <= now]
            for timer in due:
                if timer.repeat:
                    timer._due = max(timer._due + timer.seconds, now)
                else:
                    timer._finished = True
            self.timers = [t for t in self.timers if t.active]
        for timer in due:
            with self.lock:
                if not self.running: return
                if not timer._cancelled: timer.callback() # an earlier callback may have cancelled it

    def _sleep_time(self):
        """How long to wait for input: 0.05s, or less if a timer is due sooner."""
        with self.lock:
            due = min((t._due for t in self.timers if t.active), default=None)
        return 0.05 if due is None else max(0.0, min(0.05, due - time.monotonic()))

    # --- Lifetime ---

    def wait(self) -> None:
        """Block until the view is closed (quit key, view.quit(), or Ctrl+C)."""
        self._waiting = True
        try:
            while not self._done.wait(0.1):
                pass
        except KeyboardInterrupt:
            pass
        finally:
            self._waiting = False
            self.stop()
        if self._exit_code:
            raise SystemExit(self._exit_code)

    def quit(self) -> None:
        """Close the view. If the main program isn't in view.wait(), it's
        interrupted like Ctrl+C so the program ends."""
        interrupt = not self._waiting and threading.current_thread() is not threading.main_thread()
        self.stop()
        if interrupt:
            self._quitting = True
            _thread.interrupt_main() # runs our SIGINT handler in the main thread, which exits cleanly

    def stop(self) -> None:
        """Close the view and put the terminal back to normal."""
        if self.running:
            self.running = False
            if self.thread and self.thread is not threading.current_thread():
                self._wake()
                self.thread.join()
            if self.inline: self._end_inline()
            teardown(bool(self.inline), self._stderr_shown)
            self._done.set()

    # --- Inline ---

    def _start_inline(self):
        """Make room for the view under the cursor, and find which row it starts on."""
        screen_w, screen_h = screen_size()
        if self.inline is True:
            need = self._place(screen_w, 0).min_height if self.grid else 1
        else:
            need = self.inline
        rows = self._rows = max(1, min(need, screen_h))
        position = inputs.cursor_position()
        if position is None:
            row = screen_h - 1 # no answer: guess it's at the bottom, where a busy terminal's prompt is
        elif position[0] > 0:
            write("\r\n") # start on a line of our own
            row = min(position[1] + 1, screen_h - 1)
        else:
            row = position[1]
        write("\n" * (rows - 1)) # scrolls the screen up if there isn't room below
        bottom = min(row + rows - 1, screen_h - 1)
        self._top = bottom - (rows - 1)

    def _screen_area(self):
        """The size of the area the view draws in: the screen, or an inline view's rows."""
        width, height = screen_size()
        if not self.inline: return width, height
        self._rows = min(self._rows, height)
        self._top = max(0, min(self._top, height - self._rows))
        return width, self._rows

    def _has_stdout(self):
        return any(isinstance(widget, Stdout) for widget in self._every_widget())

    def _print_above(self, kind, text):
        """Print text above an inline view, a whole line at a time, moving the view down."""
        if kind == "stderr": self._stderr_shown += len(text)
        *lines, self._pending[kind] = (self._pending[kind] + text).split("\n")
        if lines: self._write_above([(kind, line) for line in lines])

    def _write_above(self, lines):
        screen_w, screen_h = screen_size()
        out, used = [move(0, self._top), ESC + "0m", ESC + "J"], 0 # clear the view, then write over it
        for kind, line in lines:
            line = line.expandtabs()
            width = text_width(ANSI_CODE.sub("", line))
            used += max(1, -(-width // max(1, screen_w))) # rows it takes, long lines wrapping
            out.append((styled(line, fg="red") if kind == "stderr" else line + ESC + "0m") + "\r\n")
        # Below the text, make room for the view again
        row = min(self._top + used, screen_h - 1)
        out.append("\n" * (self._rows - 1))
        self._top = min(row + self._rows - 1, screen_h - 1) - (self._rows - 1)
        write("".join(out))
        self._shown = None # draw it all again, in its new place
        self._redraw_base = True

    def _end_inline(self):
        """Print what's left of the printed text, then leave the last frame (or clear it)
        with the cursor below it, for the prompt."""
        rest = [(kind, text) for kind, text in self._pending.items() if text]
        self._pending = {"stdout": "", "stderr": ""}
        if rest:
            self._write_above(rest)
            with self.lock:
                self.running, running = True, self.running # _render only draws while running
                self._render()
                self.running = running
        if self.keep_on_exit:
            write(ESC + "0m" + move(0, self._top + self._rows - 1) + "\r\n")
        else:
            write(ESC + "0m" + move(0, self._top) + ESC + "J")

    # --- Internals ---

    def _wake(self):
        inputs.wake()

    def _redraw_borders(self):
        self._redraw_base = True
        self._wake()

    def _interrupt(self):
        """Ctrl+C: the terminal sends it to us as a key (so text boxes can copy with it),
        so raise it as the signal it would have been: KeyboardInterrupt in the main thread."""
        if hasattr(signal, "SIGINT") and os.name != "nt":
            os.kill(os.getpid(), signal.SIGINT)
        else:
            _thread.interrupt_main()

    def _install_sigint(self):
        """Signal handlers can only be set from the main thread, so set one up now
        that the quit key can trigger later: it ends the program with exit code 0.
        Real Ctrl+C still raises KeyboardInterrupt as usual."""
        if threading.current_thread() is not threading.main_thread(): return
        previous = signal.getsignal(signal.SIGINT)
        def handler(signum, frame):
            if self._quitting:
                raise SystemExit(self._exit_code)
            if callable(previous):
                return previous(signum, frame)
            raise KeyboardInterrupt
        signal.signal(signal.SIGINT, handler)

    def _input_loop(self):
        while self.running:
            try:
                size = self._screen_area()
                if size != self.size:
                    self.size = size
                    self._relayout = True
                for input in inputs.read_inputs(timeout=self._sleep_time()):
                    with self.lock:
                        if not self.running: return
                        self._dispatch(input)
                self._run_timers()
                self._render()
            except Exception:
                traceback.print_exc() # goes to the captured stderr, shown after the view closes
                self._exit_code = 1
                self.quit()
                return

    def _dispatch(self, input):
        if self.inline and input.type.startswith("mouse"):
            input.details["y"] -= self._top # to rows of the view, like the full screen's
        if self.inline and input.type in ("stdout", "stderr") and not self._has_stdout():
            self._print_above(input.type, input.details["text"])
            return
        inputs.update_state(input)
        if self.too_small and input.type not in ("stdout", "stderr"): # keep collecting prints
            # Nothing's laid out to get input, but quitting still works
            if input.type == "key" and input.details["key"] == "ctrl+c": self._interrupt()
            elif input.type == "key" and self.quit_key and input.details["key"] == self.quit_key \
                    and self.bindings.get(self.quit_key) == self.quit:
                self.quit()
            return

        top = self.popups[-1] if self.popups else None

        if input.type == "key":
            key, char, focused = input.details["key"], input.details["char"], self.focused
            if top and key == "escape" and top.close_on_escape:
                top.close()
                return
            if focused and focused.enabled and focused._claims_key(key):
                focused.on_input(input) # e.g. Ctrl+C copying the selection in a text box
                return
            if top and top.keep_typing and not char and key in POPUP_KEYS:
                target = next((w for w in self._walk(top.widgets) if w.can_focus), None)
                if target:
                    target.on_input(input) # e.g. arrows move through a menu while typing
                    return
            if focused and focused.captures_text and char:
                focused.on_input(input) # typing into a text box beats key bindings
            elif key in self.bindings:
                self.bindings[key]()
            elif key == "ctrl+c":
                self._interrupt()
            elif key in ("tab", "shift_tab"):
                self.focus_next(1 if key == "tab" else -1)
            elif focused and any(c._child_key(key) for c in _containers(focused)):
                pass # e.g. Ctrl+Page Down switched the tab the focused widget is in
            elif focused:
                focused.on_input(input)
            return

        if input.type == "paste":
            focused = self.focused
            if focused and focused.captures_text and focused.enabled: focused.on_input(input)
            return

        if input.type.startswith("mouse"):
            if input.type == "mouse_down" and top and not top._contains(mouse.x, mouse.y):
                if top.close_on_outside_click:
                    top.close()
                    if top.modal: return # the click only closes it
                elif top.modal:
                    return
            active = self._active_widgets()
            if input.type == "mouse_down":
                # Clicking a focusable widget focuses it (mouse_over skips covered widgets)
                for widget in reversed(active):
                    keeps_typing = widget._popup is not None and widget._popup.keep_typing
                    if widget.can_focus and widget.mouse_over() and not keeps_typing:
                        self.focus(widget)
                        break
            for widget in active:
                if widget.enabled: widget.on_input(input)
            return

        for widget in self._every_widget(): # printed text reaches hidden tabs too
            widget.on_input(input)

    def _render(self):
        """Draw a frame: redraw changed widgets, stack everything on top of the
        borders, and send only the cells that differ from what's on screen."""
        with self.lock:
            if not self.running: return
            if self._relayout:
                self._apply_layout()
            if self.too_small: return

            changed = False
            if self._redraw_base:
                self._draw_base()
                changed = True
            for popup in self.popups:
                if any(w._dirty for w in self._walk(popup.widgets)):
                    old = (popup.x, popup.y, popup.w, popup.h)
                    self._place_popup(popup) # its content may want a different size now
                    if (popup.x, popup.y, popup.w, popup.h) != old: changed = True
            for widget in self._all_widgets():
                if widget._dirty:
                    _, _, width, height = widget._draw_area()
                    canvas = Canvas(max(0, width), max(0, height))
                    widget.draw(canvas)
                    if not widget.enabled: canvas.restyle(self.theme.get("disabled", ""))
                    widget._canvas = canvas
                    widget._dirty = False # after drawing, so changes made while drawing don't loop
                    changed = True
            if not changed: return

            screen = self._base.copy()
            for widget in self._walk(self.widgets):
                if widget._canvas: self._blit(screen, widget)
            for popup in self.popups:
                screen.fill(popup.x, popup.y, popup.w, popup.h) # hide what's underneath
                self._draw_layer_borders(screen, popup)
                for widget in self._walk(popup.widgets):
                    if widget._canvas: self._blit(screen, widget)
            out = screen.diff(self._shown, self._top)
            self._shown = screen
            if out: write(render_frame(out))

    @staticmethod
    def _blit(screen, widget):
        dx, dy, _, _ = widget._draw_area()
        screen.blit(widget._canvas, widget.x + dx, widget.y + dy)

    def _apply_layout(self):
        """Give layout widgets their rectangles for the current screen size."""
        self._relayout = False
        self.too_small = False
        self._shown = None # everything gets drawn again
        if self.inline: # just our rows
            write("".join(move(0, self._top + row) + ESC + "2K" for row in range(self.size[1])))
        else:
            write(clear_screen())
        width, height = self.size
        self._base = Canvas(width, height)
        if self.grid:
            placement = self._place(width, height)
            if not placement.fits:
                self.too_small = True
                self._draw_too_small(placement.min_width, placement.min_height)
                return
            self.frames = {self.named[name]: rect for name, rect in placement.frames.items()}
            for name, (x, y, w, h) in placement.rects.items():
                widget = self.named[name]
                widget.x, widget.y, widget.width, widget.height = x, y, w, h
                widget._framed = widget in self.frames
                widget._arrange_children()
                widget.on_resize()
        for widget in self.widgets:
            if widget._group is None: widget._arrange_children() # added with view.add()
        for popup in self.popups:
            self._place_popup(popup)
        self._redraw_base = True
        for widget in self._every_widget():
            widget._dirty = True

    def _draw_base(self):
        """Draw the layout's borders. The focused widget's border is highlighted."""
        self._redraw_base = False
        width, height = self.size
        self._base = Canvas(width, height)
        self._draw_layer_borders(self._base, self)

    def _draw_layer_borders(self, canvas, layer):
        """Draw the borders of a view or popup and of the shown panels inside it, all
        at once so lines that meet join up. Titles: a widget's title (or its name,
        outside popups); a popup's title on its own border."""
        frames, titles, gaps = {}, {}, {}
        for group in self._layer_groups(layer):
            for key, frame in group.frames.items():
                if key is group:
                    frames[key] = frame
                    titles[key] = group.title if group is layer else None # a tab's name is on the tab bar
                    continue
                shapes, shape_gaps = key._border_shapes(frame) # usually just the frame itself
                frames.update(shapes)
                for cell, directions in shape_gaps.items():
                    gaps[cell] = gaps.get(cell, 0) | directions
                if shapes.get(key) != frame:
                    titles[key] = None # it draws something else in place of its frame
                elif (group is layer and isinstance(layer, Popup)) or key.name in getattr(group, "_unnamed", ()) \
                        or key._panels(): # a container's edge is its panels' too, and their titles go there
                    titles[key] = key.title
                else:
                    titles[key] = key.title or key.name
        popup = layer if isinstance(layer, Popup) else None
        focused = self.focused if self.focused is not None and self.focused._popup is popup else None
        _draw_borders(canvas, frames, titles, focused, self.theme, gaps)
        for group in self._layer_groups(layer):
            for widget in group.widgets:
                for (x, y), (char, s) in widget._border_marks().items():
                    if not (0 <= x < canvas.width and 0 <= y < canvas.height): continue
                    if char and canvas.chars[y][x] in ("│", "─"): canvas.chars[y][x] = char
                    canvas.styles[y][x] = s

    def _draw_too_small(self, need_w, need_h):
        width, height = self.size
        lines = ["Terminal too small", f"need {need_w}x{need_h}, have {width}x{height}",
                 f"{self.quit_key} or Ctrl+C to quit" if self.quit_key else "Ctrl+C to quit"]
        for i, line in enumerate(lines):
            line = fit(line, width)
            self._base.text(max(0, (width - len(line)) // 2), max(0, height // 2 - 1 + i), line)
        write(render_frame(self._base.diff(None, self._top)))
        self._shown = self._base

