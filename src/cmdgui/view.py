from __future__ import annotations

import _thread
import atexit
import collections
import os
import re
import signal
import sys
import threading
import time
import traceback
from typing import Any, Callable, Optional, TypeVar, Union
from .shorts import *
from .widgets import *
from .widgets import W
from .widgets.base import _groups
from .panel import Group, Panel, Popup, Edge, _from_position
from .layout import parse_size, LayoutError
from . import inputs

P = TypeVar("P", bound="Popup")

# With keep_typing, these keys go to the popup instead of the focused text box
POPUP_KEYS = {"up", "down", "page_up", "page_down", "enter"}

# view.notify() levels, and the icon each one shows
TOAST_ICONS = {"info": "●", "ok": "✔", "warning": "▲", "error": "✖"}
MAX_TOASTS = 5

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


def _draw_borders(canvas, frames, titles, focused, theme, gaps=None, styles=None):
    """Draw every border at once, so shared edges are one line and meeting
    lines get the right junction (├ ┬ ┼ ...). The focused frame is drawn in
    the focus colour. titles: frame key -> title (or None). gaps: (x, y) ->
    directions to leave out there, e.g. the opening under an active tab.
    styles: frame key -> border style ("single" if missing)."""
    links = {} # (x, y) -> directions that cell connects to
    kinds = {} # (x, y) -> the border style drawn there, the highest ranked of the frames on it
    def link(x, y, direction):
        links[(x, y)] = links.get((x, y), 0) | direction
        if STYLE_RANK[kind] > STYLE_RANK[kinds.get((x, y), "ascii")] or (x, y) not in kinds:
            kinds[(x, y)] = kind
    for key, (x, y, w, h) in frames.items():
        kind = (styles or {}).get(key) or "single"
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
        canvas.put(x, y, LINE_STYLES[kinds[(x, y)]][directions], theme["border"])

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


class Toast:
    """A short message in the corner of the screen, from view.notify(). It goes by itself
    after a few seconds, or when it's clicked; close() takes it away sooner."""
    def __init__(self, view: "View", message: str, level: str):
        self.message, self.level = message, level
        self._view = view
        self._timer: Optional[Timer] = None
        self._rect: Optional[tuple[int, int, int, int]] = None # where it was drawn last

    @property
    def is_open(self) -> bool:
        return self in self._view._toasts

    def close(self) -> None:
        """Take it away now (does nothing if it's gone already)."""
        self._view._close_toast(self)


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

    border_style: how borders look, unless a widget has its own: "single",
    "rounded", "heavy", "double" or "ascii".
    """
    _kind = "view"

    def __init__(self, layout: Optional[str] = None, theme: Optional[dict] = None,
                 quit_key: Optional[str] = "q", inline: Union[bool, int] = False,
                 keep_on_exit: bool = True, copy_on_select: bool = False,
                 border_style: str = "single", **widgets: Widget):
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
        if border_style not in LINE_STYLES:
            raise ValueError(f"unknown border style {border_style!r} (use {', '.join(LINE_STYLES)})")
        self.border_style = border_style # for borders without a style of their own
        self._laid_out_size = None # the size the layout was last worked out for
        self._line_hover = None # (group, edge index) of the draggable line under the mouse
        self._line_drag = None  # the same, for the one being dragged
        self._queue = collections.deque() # inputs read but not handled yet
        self._toasts: list[Toast] = [] # from notify(), oldest first
        self._generation = 0 # goes up when a dialog finishes, so input from before it is stale
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

    # --- Notifications ---

    def notify(self, message: str, level: str = "info", seconds: Optional[float] = 3) -> Toast:
        """Show a short message in the bottom right corner, over everything, for a few
        seconds: view.notify("Saved"), view.notify("Couldn't connect", "error").
        level: "info", "ok", "warning" or "error", for the icon and colour. seconds=None
        keeps it until it's clicked. It doesn't take focus or block anything, and newer
        ones stack below older ones. Safe to call from any thread."""
        if level not in TOAST_ICONS:
            raise ValueError(f"unknown level {level!r} (use {', '.join(TOAST_ICONS)})")
        toast = Toast(self, message, level)
        with self.lock:
            self._toasts.append(toast)
            for old in self._toasts[:-MAX_TOASTS]: old.close()
            if seconds is not None: toast._timer = self.after(seconds, toast.close)
            self._redraw_base = True
        self._wake()
        return toast

    def _close_toast(self, toast):
        with self.lock:
            if toast not in self._toasts: return
            self._toasts.remove(toast)
            if toast._timer: toast._timer.cancel()
            self._redraw_base = True
        self._wake()

    def _draw_toasts(self, screen):
        """The notifications, newest at the bottom right, older ones above."""
        width, height = self.size
        inner = max(4, min(44, width - 8)) # room for the text
        kind = "ascii" if self.border_style == "ascii" else "rounded"
        bottom = height - 1 # one row up from the bottom, so the layout's edge shows
        for toast in self._toasts: toast._rect = None
        for toast in reversed(self._toasts):
            plain, styles = parse_markup(str(toast.message), self.theme.get("text", ""))
            rows = wrap_spans(plain, inner)
            w = max(text_width(plain[start:end]) for start, end in rows) + 6 # border, padding, icon
            h = len(rows) + 2
            x, y = max(0, width - w - 2), bottom - h
            if y < 0: break
            edge = self.theme.get(f"toast_{toast.level}", "")
            screen.fill(x, y, w, h)
            screen.border(x, y, w, h, kind, edge)
            screen.put(x + 2, y + 1, TOAST_ICONS[toast.level], edge)
            for i, (start, end) in enumerate(rows):
                screen.styled(x + 4, y + 1 + i, plain[start:end], styles[start:end], width=w - 5)
            toast._rect = (x, y, w, h)
            bottom = y

    def _toast_at(self, x, y):
        return next((t for t in self._toasts if t._rect and t._rect[0] <= x < t._rect[0] + t._rect[2]
                     and t._rect[1] <= y < t._rect[1] + t._rect[3]), None)

    # --- Dialogs that wait for an answer ---

    def confirm(self, message: str, title: Optional[str] = None,
                yes: str = "OK", no: str = "Cancel") -> bool:
        """Ask a yes/no question and wait for the answer: True for yes, False for no or
        Escape. Works from your own code and from callbacks (the view keeps running
        while it waits):

            if view.confirm("Delete notes.txt?", yes="Delete"):
                os.remove("notes.txt")"""
        answer = []
        popup = Popup("message - \n yes no", message=Text(message, align="center"),
                      yes=Button(yes), no=Button(no), title=title)
        popup.yes.on_click(lambda: (answer.append(True), popup.close()))
        popup.no.on_click(popup.close)
        self._wait_for(popup)
        return bool(answer)

    def prompt(self, message: str, value: str = "", title: Optional[str] = None,
               placeholder: str = "", password: bool = False) -> Optional[str]:
        """Ask for some text and wait for it: what was typed, or None if cancelled.
        value is the text to start with.

            name = view.prompt("Rename to:", value=old_name)
            if name: ..."""
        answer = []
        def ok():
            answer.append(popup.input.value)
            popup.close()
        popup = Popup("message - \n input - \n ok cancel", message=Text(message),
                      input=TextInput(value, placeholder=placeholder, password=password, cursor=len(value),
                                      border=True, preferred_width="30+", on_submit=lambda _: ok()),
                      ok=Button("OK", on_click=ok), cancel=Button("Cancel"), title=title)
        popup.cancel.on_click(popup.close)
        self._wait_for(popup)
        return answer[0] if answer else None

    def choose(self, items: list, message: Optional[str] = None, title: Optional[str] = None,
               selected: int = 0) -> Any:
        """Ask for one of a list of items and wait for it: the item picked (with Enter
        or a click), or None if cancelled.

            editor = view.choose(["vim", "nano", "code"], "Open with:")"""
        answer = []
        def pick(index, item):
            answer.append(item)
            popup.close()
        menu = Menu(items, selected=selected, on_select=pick)
        if message is None:
            popup = Popup("menu", menu=menu, title=title)
        else:
            popup = Popup("message \n menu", message=Text(message), menu=menu, title=title)
        self._wait_for(popup)
        return answer[0] if answer else None

    def _wait_for(self, popup):
        """Show a popup and return once it's closed (or the view stops)."""
        closed = threading.Event()
        popup.on_close(closed.set)
        popup._dialog = True
        self.show(popup)
        if threading.current_thread() is not self.thread:
            while self.running and not closed.wait(0.05): # your own code: just wait
                pass
            return
        # In a callback, on the view's own thread: keep the view going from here until it
        # closes. The lock is let go meanwhile, so other threads can still use the view.
        saved = self.lock._release_save() if self.lock._is_owned() else None
        try:
            while self.running and not closed.is_set():
                self._step()
        finally:
            if saved is not None: self.lock._acquire_restore(saved)
            self._generation += 1 # the input that opened it is old news now

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
        """The widgets being shown, each followed by the widgets shown inside it, all
        the way down. hidden=True: every widget, hidden ones and all tabs too."""
        for widget in widgets:
            if not hidden and not widget.visible: continue
            yield widget
            yield from View._walk(widget._inside(hidden), hidden)

    @staticmethod
    def _layer_groups(group):
        """A view or popup, and every shown panel (and Tabs) inside it."""
        yield group
        for widget in View._walk(group.widgets):
            if isinstance(widget, Group): yield widget

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
        """Size the popup to its content (or its preferred size) and position it."""
        screen_w, screen_h = self.size
        natural = popup._place(0, 0, fit_content=True, outer=popup.border)
        edges = 2 if popup.border else 0
        def size(preferred, natural, screen):
            if preferred is not None:
                low, high = parse_size(preferred)
                natural = max(low + edges, natural if high is None else min(natural, high + edges))
            return min(natural, screen)
        w = size(popup.preferred_width, natural.min_width, screen_w)
        h = size(popup.preferred_height, natural.min_height, screen_h)

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

        popup.x, popup.y, popup.width, popup.height = x, y, w, h
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
            focusable = [w for w in self._active_widgets() if w.can_focus and w.tab_stop]
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
                self._step()
            except Exception:
                traceback.print_exc() # goes to the captured stderr, shown after the view closes
                self._exit_code = 1
                self.quit()
                return

    def _step(self):
        """One go round the loop: notice a resize, handle input, run timers and draw.
        A dialog opened from a callback runs this too, until it's answered."""
        size = self._screen_area()
        if size != self.size:
            self.size = size
            self._relayout = True
        # Inputs go through a queue, so ones read before a dialog opened are handled
        # (by the dialog's loop) before newer ones
        self._queue.extend(inputs.read_inputs(timeout=0 if self._queue else self._sleep_time()))
        while self._queue:
            input = self._queue.popleft()
            with self.lock:
                if not self.running: return
                self._dispatch(input)
        self._run_timers()
        self._render()

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
            if focused and focused._usable and focused._claims_key(key):
                focused.on_input(input) # e.g. Ctrl+C copying the selection in a text box
                return
            if top and top.keep_typing and not char and key in POPUP_KEYS:
                target = next((w for w in self._walk(top.widgets) if w.can_focus), None)
                if target:
                    target.on_input(input) # e.g. arrows move through a menu while typing
                    return
            if focused and focused.captures_text and char:
                focused.on_input(input) # typing into a text box beats key bindings
            elif key in self.bindings and not (key != self.quit_key and any(p._dialog for p in self.popups)):
                self.bindings[key]() # not while a dialog waits for an answer, except to quit
            elif key == "ctrl+c":
                self._interrupt()
            elif key in ("tab", "shift_tab"):
                self.focus_next(1 if key == "tab" else -1)
            elif focused and any(g._child_key(key) for g in _groups(focused) if isinstance(g, Widget)):
                pass # e.g. Ctrl+Page Down switched the tab the focused widget is in
            elif focused:
                focused.on_input(input)
            return

        if input.type == "paste":
            focused = self.focused
            if focused and focused.captures_text and focused._usable: focused.on_input(input)
            return

        if input.type.startswith("mouse"):
            toast = None if self._line_drag else self._toast_at(mouse.x, mouse.y)
            if toast is not None:
                if input.type == "mouse_down": toast.close() # a click dismisses it
                return
            if self._line_input(input): return
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
            generation = self._generation
            for widget in active:
                if self._generation != generation: break # a dialog came and went: the click was for it
                if widget._usable: widget.on_input(input)
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
                    old = (popup.x, popup.y, popup.width, popup.height)
                    self._place_popup(popup) # its content may want a different size now
                    if (popup.x, popup.y, popup.width, popup.height) != old: changed = True
            for widget in self._all_widgets():
                if widget._dirty:
                    _, _, width, height = widget._draw_area()
                    canvas = Canvas(max(0, width), max(0, height))
                    widget.draw(canvas)
                    if not widget._usable: canvas.restyle(self.theme.get("disabled", ""))
                    widget._canvas = canvas
                    widget._dirty = False # after drawing, so changes made while drawing don't loop
                    changed = True
            if not changed: return

            screen = self._base.copy()
            for widget in self._walk(self.widgets):
                if widget._canvas: self._blit(screen, widget)
            for popup in self.popups:
                screen.fill(popup.x, popup.y, popup.width, popup.height) # hide what's underneath
                self._draw_layer_borders(screen, popup)
                for widget in self._walk(popup.widgets):
                    if widget._canvas: self._blit(screen, widget)
            if self._toasts: self._draw_toasts(screen)
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
        if self.size != self._laid_out_size: # a new size: start from a clean screen
            self._laid_out_size = self.size
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
            self._place_lines(placement, 0, 0)
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
        frames, titles, gaps, styles = {}, {}, {}, {}
        popup = layer if isinstance(layer, Popup) else None
        if popup is not None and popup.border:
            frames[popup] = (popup.x, popup.y, popup.width, popup.height)
            titles[popup], styles[popup] = popup.title, popup.border_style
        for group in self._layer_groups(layer):
            for key, frame in group.frames.items():
                shapes, shape_gaps = key._border_shapes(frame) # usually just the frame itself
                frames.update(shapes)
                for shape in shapes: styles[shape] = group._frame_style(shape)
                for cell, directions in shape_gaps.items():
                    gaps[cell] = gaps.get(cell, 0) | directions
                # Nothing if it draws something else in place of its frame
                titles[key] = group._frame_title(key) if shapes.get(key) == frame else None
        focused = self.focused if self.focused is not None and self.focused._popup is popup else None
        styles = {key: styles.get(key) or self.border_style for key in frames}
        _draw_borders(canvas, frames, titles, focused, self.theme, gaps, styles)
        for group in self._layer_groups(layer):
            marks = [widget._border_marks() for widget in group.widgets] + [self._line_marks(group, canvas)]
            for (x, y), (char, s) in (item for widget_marks in marks for item in widget_marks.items()):
                if not (0 <= x < canvas.width and 0 <= y < canvas.height): continue
                if char and canvas.chars[y][x] in ("│", "─"): canvas.chars[y][x] = char
                canvas.styles[y][x] = s

    # --- Draggable lines ---

    def _line_marks(self, group, canvas):
        """A grip (a short heavy line) on each draggable line, as near its middle as it
        goes without crossing a junction, and the whole line lit up under the mouse or
        while dragged."""
        marks = {}
        for index, (x, y, w, h) in group._lines.items():
            vertical = group._spans[index][0] == "x"
            cells = [(x, y + i) for i in range(h)] if vertical else [(x + i, y) for i in range(w)]
            active = (group, index) in (self._line_hover, self._line_drag)
            if active:
                for cell in cells: marks[cell] = (None, self.theme.get("divider_hover", ""))
            plain = [0 <= cx < canvas.width and 0 <= cy < canvas.height and canvas.chars[cy][cx] in ("│", "─")
                     for cx, cy in cells]
            size = 3 if len(cells) >= 9 else 1
            middle = (len(cells) - size) // 2
            starts = [i for i in range(len(cells) - size + 1) if all(plain[i:i + size])]
            if not starts and size > 1:
                size = 1
                starts = [i for i, ok in enumerate(plain) if ok]
            if not starts: continue
            start = min(starts, key=lambda i: abs(i - middle))
            for cell in cells[start:start + size]:
                marks[cell] = ("┃" if vertical else "━", self.theme.get("divider_hover" if active else "border", ""))
        return marks

    def _line_at(self, x, y):
        """(group, edge index) of the draggable line at (x, y), if there's one there
        and nothing's covering it."""
        layer = self._layer_at(x, y)
        modal = next((i for i in range(len(self.popups) - 1, -1, -1) if self.popups[i].modal), None)
        if modal is not None and (layer is None or self.popups.index(layer) < modal): return None
        for group in self._layer_groups(layer or self):
            for index, (lx, ly, lw, lh) in group._lines.items():
                if lx <= x < lx + lw and ly <= y < ly + lh: return group, index
        return None

    def _set_line_hover(self, over):
        if over != self._line_hover:
            self._line_hover = over
            self._redraw_borders()

    def _line_input(self, input):
        """Drag the draggable lines. Returns True if the input was used for that."""
        if self._line_drag:
            if input.type == "mouse_move" and mouse.is_down(0):
                self._drag_line(*self._line_drag)
                return True
            if input.type in ("mouse_up", "mouse_move"):
                self._line_drag = self._line_hover = None
                self._set_line_hover(self._line_at(mouse.x, mouse.y))
                self._redraw_borders()
                return True
            return False
        over = self._line_at(mouse.x, mouse.y)
        if input.type in ("mouse_move", "mouse_down", "mouse_up"): self._set_line_hover(over)
        if input.type == "mouse_down" and input.details.get("button") == 0 and over:
            self._line_drag = over
            self._redraw_borders()
            return True
        return False

    def _drag_line(self, group, index):
        """Move a draggable line to the mouse, keeping its position the same kind of number."""
        if index not in group._spans: return
        axis, start, room, low, high, _ = group._spans[index]
        if room <= 0: return
        line = group._edges[index]
        at = max(low, min(high, mouse.x if axis == "x" else mouse.y))
        kind, side, _ = line.position or ("share", 0, 0)
        size = at - start if side == 0 else room - (at - start)
        position = (kind, side, size / room if kind == "share" else size)
        if position == line.position: return
        line.position = position
        self.relayout()
        if line.callback:
            callback, flipped = line.callback
            callback(_from_position(position, flipped))

    def _draw_too_small(self, need_w, need_h):
        width, height = self.size
        lines = ["Terminal too small", f"need {need_w}x{need_h}, have {width}x{height}",
                 f"{self.quit_key} or Ctrl+C to quit" if self.quit_key else "Ctrl+C to quit"]
        for i, line in enumerate(lines):
            line = fit(line, width)
            self._base.text(max(0, (width - len(line)) // 2), max(0, height // 2 - 1 + i), line)
        write(render_frame(self._base.diff(None, self._top)))
        self._shown = self._base

