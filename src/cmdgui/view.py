from __future__ import annotations

import _thread
import atexit
import signal
import sys
import threading
import traceback
import copy
from typing import Any, Callable, Optional, TypeVar, Union
from .shorts import *
from .widgets import *
from .widgets import W
from .layout import parse_layout, parse_size, place, LayoutError
from . import inputs

P = TypeVar("P", bound="Popup")

# With keep_typing, these keys go to the popup instead of the focused text box
POPUP_KEYS = {"up", "down", "page_up", "page_down", "enter"}

# Setup terminal
def setup():
    write(ESC + "?1049h" + hide_cursor()) # alternative screen
    inputs.enable()

def teardown():
    inputs.disable()
    write(show_cursor() + ESC + "?1049l") # back to the normal screen
    # Anything written to stderr (like a traceback) was hidden on the alternate screen
    errors = inputs.captured_stderr()
    if errors:
        sys.stderr.write(errors)
        sys.stderr.flush()


def _draw_borders(canvas, frames, titles, focused, theme):
    """Draw every border at once, so shared edges are one line and meeting
    lines get the right junction (├ ┬ ┼ ...). The focused frame is drawn in
    the focus colour. titles: frame name -> title (or None)."""
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
        self.frames: dict[Any, tuple[int, int, int, int]] = {} # name -> border rectangle

        # Class attributes (copied, so each instance gets its own) and keyword arguments
        provided: dict[str, Any] = {}
        for klass in reversed(type(self).__mro__):
            for name, value in vars(klass).items():
                if isinstance(value, (Widget, Popup)):
                    provided[name] = value.copy()
        for name, value in widgets.items():
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
            self.widgets.append(widget)
            self.named[name] = widget
        for name, widget in self.named.items():
            self.__dict__[name] = widget # group.name finds this instance's copy, not the class attribute

    def _add_popup(self, name, popup) -> None:
        raise TypeError(f"{type(self).__name__}() got a popup '{name}', only views can hold popups")

    def _default_layout(self, provided):
        return None

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
            if fit_content:
                content_w, content_h = widget.content_size()
                sizes[name] = (_spec(widget.preferred_width, content_w), _spec(widget.preferred_height, content_h))
            else:
                sizes[name] = (widget.preferred_width, widget.preferred_height)
            slot_border = self.grid.slots[name].border
            borders[name] = widget.border if slot_border is None else slot_border
        return place(self.grid, width, height, sizes, borders, outer=outer)


class Popup(Group):
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

    A popup with one widget doesn't need a layout: Popup(Menu(items)), or a
    subclass with a single widget attribute.
    Settings can be class attributes or constructor arguments."""
    _kind = "popup"
    modal: bool = True                    # block everything underneath while open
    close_on_escape: bool = True
    close_on_outside_click: bool = False
    keep_typing: bool = False             # the focused text box keeps getting typed text; arrows and Enter come here
    border: bool = True
    title: Optional[str] = None
    width: Optional[int] = None           # outer size, including the border; None to fit the content
    height: Optional[int] = None

    def __init__(self, layout: Union[str, Widget, None] = None, *,
                 modal: Optional[bool] = None, close_on_escape: Optional[bool] = None,
                 close_on_outside_click: Optional[bool] = None, keep_typing: Optional[bool] = None,
                 border: Optional[bool] = None, title: Optional[str] = None,
                 width: Optional[int] = None, height: Optional[int] = None,
                 on_close: Optional[Callable[[], Any]] = None, **widgets: Widget):
        settings = dict(modal=modal, close_on_escape=close_on_escape, keep_typing=keep_typing,
                        close_on_outside_click=close_on_outside_click, border=border,
                        title=title, width=width, height=height)
        for key, value in settings.items():
            if value is not None: setattr(self, key, value)
        self.close_callback = on_close
        self.view: Optional[View] = None
        self.x = self.y = self.w = self.h = 0 # on screen, including the border
        self._anchor: tuple[str, Any] = ("center", None)
        self._previous_focus: Optional[Widget] = None

        if isinstance(layout, Widget):
            widgets = {"content": layout, **widgets}
            layout = None
        self._init_group(layout, widgets)
        if not self.grid:
            raise LayoutError("a popup needs a layout or at least one widget")
        self.init()

    def _default_layout(self, provided):
        return next(iter(provided)) if len(provided) == 1 else None # a single widget fills the popup

    def init(self) -> None:
        """Override to wire up widgets, e.g. self.no.on_click(self.close)."""

    @property
    def is_open(self) -> bool:
        return self.view is not None

    def on_close(self, callback: Optional[Callable[[], Any]]) -> None:
        """Call callback() whenever the popup closes."""
        self.close_callback = callback

    def close(self) -> None:
        """Close the popup (does nothing if it isn't open)."""
        if self.view: self.view._close(self)

    def copy(self: P) -> P:
        """A separate copy with its own widgets (init() runs again for it)."""
        new = copy.copy(self)
        new.__dict__.update(view=None, widgets=[], named={}, frames={}, _previous_focus=None)
        for name, widget in self.named.items():
            widget = widget.copy()
            widget.name = name
            new.widgets.append(widget)
            new.named[name] = widget
            new.__dict__[name] = widget
        new.init()
        return new

    def _contains(self, x, y):
        return self.x <= x < self.x + self.w and self.y <= y < self.y + self.h


class View(Group):
    """A terminal GUI. Three ways to fill it, which can be mixed:

        View("label[heading] \n stdout")                  # types in the layout
        View("heading \n stdout", heading=Label("Hi"))    # widgets passed in

        class UI(View):                                    # a subclass: typed in your editor
            layout = "heading \n stdout"
            heading = Label("Hi")
    """
    _kind = "view"

    def __init__(self, layout: Optional[str] = None, theme: Optional[dict] = None,
                 quit_key: Optional[str] = "q", **widgets: Widget):
        self.lock = threading.RLock() # reentrant, so widgets can call view methods while handling input
        self.running = False
        self.thread = None
        self.too_small = False
        self.focused: Optional[Widget] = None
        self.theme = {**DEFAULT_THEME, **(theme or {})}
        self.bindings = {} # key name -> function
        self.size = (0, 0)
        self._base = None   # borders (or the "too small" message), widgets go on top
        self._shown = None  # what's on the terminal right now
        self._relayout = True
        self._redraw_base = True
        self._done = threading.Event()
        self._waiting = False
        self._quitting = False
        self._exit_code = 0 # 1 after a crash inside the view (e.g. in a callback)
        if quit_key:
            self.bindings[quit_key] = self.quit

        self.popups: list[Popup] = [] # open popups, bottom to top

        # Before touching the terminal, so a layout mistake doesn't leave it in raw mode
        self._init_group(layout, widgets)
        for widget in self.widgets:
            widget.view = self
        if self.grid:
            self._place(0, 0) # checks the widgets' sizes are valid, before touching the terminal

        self._install_sigint()
        self.running = True
        atexit.register(self.stop)
        try:
            setup()
            self.size = screen_size()
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
            widget.view = self
            self.widgets.append(widget)
        widget.refresh()
        return widget

    def refresh(self) -> None:
        """Redraw everything on the next frame."""
        for widget in self._all_widgets():
            widget._dirty = True
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
                for widget in popup.widgets:
                    widget.view = self
                    widget._popup = popup
                    widget._dirty = True
                self.popups.append(popup)
                self._place_popup(popup)
                self._redraw_base = True
                popup._previous_focus = self.focused
                if not popup.keep_typing:
                    self.focus(next((w for w in popup.widgets if w.focusable), None))
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
            for widget in popup.widgets:
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

    def _all_widgets(self):
        return self.widgets + [w for popup in self.popups for w in popup.widgets]

    def _active_widgets(self):
        """Widgets that can get mouse input and focus: everything above the top modal popup."""
        for i in range(len(self.popups) - 1, -1, -1):
            if self.popups[i].modal:
                return [w for popup in self.popups[i:] for w in popup.widgets]
        return self._all_widgets()

    def _layer_at(self, x, y):
        """The topmost popup at (x, y), or None for the main layout."""
        for popup in reversed(self.popups):
            if popup._contains(x, y):
                return popup
        return None

    def _box(self, widget):
        """A widget's rectangle including its border."""
        frames = widget._popup.frames if widget._popup else self.frames
        return frames.get(widget.name) or (widget.x, widget.y, widget.width, widget.height)

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

        placement = popup._place(w, h, fit_content=True, outer=popup.border)
        inner = 1 if popup.border else 0
        popup.x, popup.y, popup.w, popup.h = x, y, w, h
        popup.frames = {name: (x + fx, y + fy, fw, fh) for name, (fx, fy, fw, fh) in placement.frames.items()}
        if popup.border:
            popup.frames[None] = (x, y, w, h)
        for name, (rx, ry, rw, rh) in placement.rects.items():
            widget = popup.named[name]
            # Clip to the inside of the popup, in case the screen is too small for it
            rw = max(0, min(rw, w - inner - rx))
            rh = max(0, min(rh, h - inner - ry))
            if (widget.x, widget.y, widget.width, widget.height) != (x + rx, y + ry, rw, rh):
                widget.x, widget.y, widget.width, widget.height = x + rx, y + ry, rw, rh
                widget._dirty = True
                widget.on_resize()

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
            focusable = [w for w in self._active_widgets() if w.focusable]
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
            teardown()
            self._done.set()

    # --- Internals ---

    def _wake(self):
        inputs.wake()

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
                size = screen_size()
                if size != self.size:
                    self.size = size
                    self._relayout = True
                for input in inputs.read_inputs(timeout=0.05):
                    with self.lock:
                        if not self.running: return
                        self._dispatch(input)
                self._render()
            except Exception:
                traceback.print_exc() # goes to the captured stderr, shown after the view closes
                self._exit_code = 1
                self.quit()
                return

    def _dispatch(self, input):
        inputs.update_state(input)
        if self.too_small and input.type not in ("stdout", "stderr"): return # keep collecting prints

        top = self.popups[-1] if self.popups else None

        if input.type == "key":
            key, char, focused = input.details["key"], input.details["char"], self.focused
            if top and key == "escape" and top.close_on_escape:
                top.close()
                return
            if top and top.keep_typing and not char and key in POPUP_KEYS:
                target = next((w for w in top.widgets if w.focusable), None)
                if target:
                    target.on_input(input) # e.g. arrows move through a menu while typing
                    return
            if focused and focused.captures_text and char:
                focused.on_input(input) # typing into a text box beats key bindings
            elif key in self.bindings:
                self.bindings[key]()
            elif key in ("tab", "shift_tab"):
                self.focus_next(1 if key == "tab" else -1)
            elif focused:
                focused.on_input(input)
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
                    if widget.focusable and widget.mouse_over() and not keeps_typing:
                        self.focus(widget)
                        break
            for widget in active:
                widget.on_input(input)
            return

        for widget in self._all_widgets():
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
                if any(w._dirty for w in popup.widgets):
                    old = (popup.x, popup.y, popup.w, popup.h)
                    self._place_popup(popup) # its content may want a different size now
                    if (popup.x, popup.y, popup.w, popup.h) != old: changed = True
            for widget in self._all_widgets():
                if widget._dirty:
                    canvas = Canvas(max(0, widget.width), max(0, widget.height))
                    widget.draw(canvas)
                    widget._canvas = canvas
                    widget._dirty = False # after drawing, so changes made while drawing don't loop
                    changed = True
            if not changed: return

            screen = self._base.copy()
            for widget in self.widgets:
                if widget._canvas: screen.blit(widget._canvas, widget.x, widget.y)
            for popup in self.popups:
                screen.fill(popup.x, popup.y, popup.w, popup.h) # hide what's underneath
                titles: dict[Any, Optional[str]] = {name: w.title for name, w in popup.named.items()}
                titles[None] = popup.title
                focused = self.focused.name if self.focused and self.focused._popup is popup else False
                _draw_borders(screen, popup.frames, titles, focused, self.theme)
                for widget in popup.widgets:
                    if widget._canvas: screen.blit(widget._canvas, widget.x, widget.y)
            out = screen.diff(self._shown)
            self._shown = screen
            if out: write(render_frame(out))

    def _apply_layout(self):
        """Give layout widgets their rectangles for the current screen size."""
        self._relayout = False
        self.too_small = False
        self._shown = None # everything gets drawn again
        write(clear_screen())
        width, height = self.size
        self._base = Canvas(width, height)
        if self.grid:
            placement = self._place(width, height)
            if not placement.fits:
                self.too_small = True
                self._draw_too_small(placement.min_width, placement.min_height)
                return
            for name, (x, y, w, h) in placement.rects.items():
                widget = self.named[name]
                widget.x, widget.y, widget.width, widget.height = x, y, w, h
                widget.on_resize()
            self.frames = placement.frames
        for popup in self.popups:
            self._place_popup(popup)
        self._redraw_base = True
        for widget in self._all_widgets():
            widget._dirty = True

    def _draw_base(self):
        """Draw the layout's borders. The focused widget's border is highlighted."""
        self._redraw_base = False
        width, height = self.size
        self._base = Canvas(width, height)
        titles = {name: self.named[name].title or name for name in self.frames}
        focused = self.focused.name if self.focused and self.focused._popup is None else None
        _draw_borders(self._base, self.frames, titles, focused, self.theme)

    def _draw_too_small(self, need_w, need_h):
        width, height = self.size
        lines = ["Terminal too small", f"need {need_w}x{need_h}, have {width}x{height}"]
        for i, line in enumerate(lines):
            line = fit(line, width)
            self._base.text(max(0, (width - len(line)) // 2), max(0, height // 2 - 1 + i), line)
        write(render_frame(self._base.diff(None)))
        self._shown = self._base

