import atexit
import sys
import threading
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

class CMDGUI_View():
    # Instance attributes, so widget names can't shadow them
    _ATTRS = {"widgets", "named", "lock", "running", "layout", "size", "thread", "too_small"}

    def __init__(self, layout:str = None):
        self.widgets = []
        self.named = {} # name -> widget, for widgets from the layout
        self.lock = threading.RLock() # reentrant, so refresh() works from inside on_input
        self.running = False
        self.thread = None
        self.too_small = False

        # Parse before touching the terminal, so a layout mistake doesn't leave it in raw mode
        self.layout = parse_layout(layout, types=WIDGET_TYPES) if layout else None
        if self.layout:
            for name, slot in self.layout.slots.items():
                if hasattr(type(self), name) or name in self._ATTRS:
                    raise LayoutError(f"widget name '{name}' clashes with view.{name}, pick another name")
                widget = WIDGET_TYPES[slot.type]()
                widget.name = name
                widget.view = self
                self.widgets.append(widget)
                self.named[name] = widget
            self._place(0, 0) # checks the widgets' sizes are valid, before touching the terminal

        setup()
        self.running = True
        atexit.register(self.stop)
        try:
            self.size = screen_size()
            with self.lock:
                self._apply_layout()
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

    def add(self, widget):
        with self.lock:
            widget.view = self
            self.widgets.append(widget)
            widget.super_draw()
        return widget

    def draw(self):
        with self.lock:
            for widget in self.widgets:
                widget.super_draw()

    def stop(self):
        if self.running:
            self.running = False
            if self.thread and self.thread is not threading.current_thread():
                self.thread.join()
            teardown()

    def _has_border(self, name):
        slot_border = self.layout.slots[name].border
        return self.named[name].border if slot_border is None else slot_border

    def _place(self, width, height):
        sizes = {name: (w.preferred_width, w.preferred_height) for name, w in self.named.items()}
        borders = {name: self._has_border(name) for name in self.named}
        return place(self.layout, width, height, sizes, borders)

    def _apply_layout(self):
        """Give layout widgets their rectangles for the current screen size, then redraw everything."""
        write(clear_screen())
        self.too_small = False
        if self.layout:
            placement = self._place(*self.size)
            if not placement.fits:
                self.too_small = True
                self._draw_too_small(placement.min_width, placement.min_height)
                return
            for name, (x, y, w, h) in placement.rects.items():
                widget = self.named[name]
                widget.x, widget.y, widget.width, widget.height = x, y, w, h
                widget.super_on_resize()
            self._draw_borders(placement.frames)
        for widget in self.widgets:
            widget.super_draw()

    def _draw_borders(self, frames):
        """Draw every border at once, so shared edges are one line and meeting
        lines get the right junction (├ ┬ ┼ ...)."""
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
        cells = {pos: LINE_CHARS[d] for pos, d in links.items()}

        # Titles go on the top edge, stopping before any junction
        for name, (x, y, w, h) in frames.items():
            title = self.named[name].title or name
            for i, char in enumerate(f" {title} "):
                cx = x + 2 + i
                if cx > x + w - 3 or links.get((cx, y)) != LEFT | RIGHT: break
                cells[(cx, y)] = char

        out = []
        last = None
        for (x, y) in sorted(cells, key=lambda pos: (pos[1], pos[0])):
            if last != (x - 1, y):
                out.append(move(x, y))
            out.append(cells[(x, y)])
            last = (x, y)
        write(render_frame("".join(out)))

    def _draw_too_small(self, need_w, need_h):
        width, height = self.size
        lines = ["Terminal too small", f"need {need_w}x{need_h}, have {width}x{height}"]
        out = []
        for i, line in enumerate(lines):
            line = fit(line, width)
            out.append(move(max(0, (width - len(line)) // 2), max(0, height // 2 - 1 + i)) + line)
        write(render_frame("".join(out)))

    def _input_loop(self):
        while self.running:
            size = screen_size()
            if size != self.size:
                with self.lock:
                    self.size = size
                    self._apply_layout()
            for input in inputs.read_inputs(timeout=0.05):
                with self.lock:
                    inputs.update_state(input)
                    if self.too_small and input.type != "stdout": continue # keep collecting prints
                    for widget in self.widgets:
                        widget.super_on_input(input)
