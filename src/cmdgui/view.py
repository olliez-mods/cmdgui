import _thread
import atexit
import signal
import sys
import threading
import traceback
from .shorts import *
from .widgets import *
from .layout import parse_layout, place, LayoutError
from . import inputs

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


class View():
    def __init__(self, layout:str = None, theme:dict = None, quit_key = "q"):
        self.widgets = []
        self.named = {} # name -> widget, for widgets from the layout
        self.lock = threading.RLock() # reentrant, so widgets can call view methods while handling input
        self.running = False
        self.thread = None
        self.too_small = False
        self.focused = None
        self.theme = {**DEFAULT_THEME, **(theme or {})}
        self.bindings = {} # key name -> function
        self.size = (0, 0)
        self.frames = {} # name -> border rectangle
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

        # Parse before touching the terminal, so a layout mistake doesn't leave it in raw mode
        self.layout = parse_layout(layout, types=WIDGET_TYPES) if layout else None
        if self.layout:
            for name, slot in self.layout.slots.items():
                if name in self.__dict__ or hasattr(type(self), name):
                    raise LayoutError(f"widget name '{name}' clashes with view.{name}, pick another name")
                widget = WIDGET_TYPES[slot.type]()
                widget.name = name
                widget.view = self
                self.widgets.append(widget)
                self.named[name] = widget
            self._place(0, 0) # checks the widgets' sizes are valid, before touching the terminal

        self._install_sigint()
        setup()
        self.running = True
        atexit.register(self.stop)
        try:
            self.size = screen_size()
            self._render()
            self.thread = threading.Thread(target=self._input_loop, daemon=True)
            self.thread.start()
        except BaseException:
            self.stop() # restore the terminal so the error is visible
            raise

    def __getitem__(self, name):
        return self.named[name]

    def __getattr__(self, name):
        # Only called for attributes that don't exist, so view.start finds the widget "start"
        named = self.__dict__.get("named", {})
        if name in named:
            return named[name]
        raise AttributeError(f"view has no attribute or widget named '{name}'")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()
        return False

    # --- Widgets ---

    def add(self, widget):
        """Add a widget outside the layout. Set its x, y, width, height yourself."""
        with self.lock:
            widget.view = self
            self.widgets.append(widget)
        widget.refresh()
        return widget

    def refresh(self):
        """Redraw everything on the next frame."""
        for widget in self.widgets:
            widget._dirty = True
        self._wake()

    def relayout(self):
        """Work out the layout again, e.g. after a widget's preferred size changed."""
        self._relayout = True
        self._wake()

    # --- Focus and keys ---

    def focus(self, widget):
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

    def focus_next(self, step=1):
        """Move focus to the next (or previous, step=-1) focusable widget."""
        with self.lock:
            focusable = [w for w in self.widgets if w.focusable]
            if not focusable: return
            if self.focused in focusable:
                index = (focusable.index(self.focused) + step) % len(focusable)
            else:
                index = 0 if step > 0 else -1
            self.focus(focusable[index])

    def on_key(self, key, callback):
        """Call callback() when key is pressed, e.g. view.on_key("ctrl+s", save).
        Pass None to remove a binding."""
        if callback: self.bindings[key] = callback
        else: self.bindings.pop(key, None)

    # --- Lifetime ---

    def wait(self):
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

    def quit(self):
        """Close the view. If the main program isn't in view.wait(), it's
        interrupted like Ctrl+C so the program ends."""
        interrupt = not self._waiting and threading.current_thread() is not threading.main_thread()
        self.stop()
        if interrupt:
            self._quitting = True
            _thread.interrupt_main() # runs our SIGINT handler in the main thread, which exits cleanly

    def stop(self):
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

    def _has_border(self, name):
        slot_border = self.layout.slots[name].border
        return self.named[name].border if slot_border is None else slot_border

    def _place(self, width, height):
        sizes = {name: (w.preferred_width, w.preferred_height) for name, w in self.named.items()}
        borders = {name: self._has_border(name) for name in self.named}
        return place(self.layout, width, height, sizes, borders)

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

        if input.type == "key":
            key, focused = input.details["key"], self.focused
            if focused and focused.captures_text and input.details["char"]:
                focused.on_input(input) # typing into a text box beats key bindings
            elif key in self.bindings:
                self.bindings[key]()
            elif key in ("tab", "shift_tab"):
                self.focus_next(1 if key == "tab" else -1)
            elif focused:
                focused.on_input(input)
            return

        if input.type == "mouse_down":
            # Clicking a focusable widget focuses it; the topmost one wins
            for widget in reversed(self.widgets):
                if widget.focusable and widget.mouse_over():
                    self.focus(widget)
                    break

        for widget in self.widgets:
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
            for widget in self.widgets:
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
        if self.layout:
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
        self._redraw_base = True
        for widget in self.widgets:
            widget._dirty = True

    def _draw_base(self):
        """Draw every border at once, so shared edges are one line and meeting
        lines get the right junction (├ ┬ ┼ ...). The focused widget's border
        is drawn last, in the focus colour."""
        self._redraw_base = False
        width, height = self.size
        self._base = Canvas(width, height)
        links = {} # (x, y) -> directions that cell connects to
        def link(x, y, direction):
            links[(x, y)] = links.get((x, y), 0) | direction
        for x, y, w, h in self.frames.values():
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
            self._base.put(x, y, LINE_CHARS[directions], self.theme["border"])

        focused = self.focused.name if self.focused else None
        for name, (x, y, w, h) in self.frames.items():
            if name == focused:
                s = self.theme["border_focus"]
                for cx in range(x, x + w):
                    for cy in (y, y + h - 1):
                        self._base.styles[cy][cx] = s
                for cy in range(y, y + h):
                    for cx in (x, x + w - 1):
                        self._base.styles[cy][cx] = s
            # Title on the top edge, stopping before any junction
            title = self.named[name].title or name
            title_style = self.theme["border_focus"] if name == focused else self.theme["title"]
            cx = x + 2
            for char in f" {title} ":
                if cx > x + w - 3 or links.get((cx, y)) != LEFT | RIGHT: break
                cx += self._base.put(cx, y, char, title_style)

    def _draw_too_small(self, need_w, need_h):
        width, height = self.size
        lines = ["Terminal too small", f"need {need_w}x{need_h}, have {width}x{height}"]
        for i, line in enumerate(lines):
            line = fit(line, width)
            self._base.text(max(0, (width - len(line)) // 2), max(0, height // 2 - 1 + i), line)
        write(render_frame(self._base.diff(None)))
        self._shown = self._base

