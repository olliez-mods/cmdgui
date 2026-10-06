import re
from .shorts import *
from .inputs import Input, mouse

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
}

# Changing these means the layout has to be worked out again
LAYOUT_ATTRS = {"preferred_width", "preferred_height", "border", "title"}
# Set by the view, so changing them shouldn't trigger a redraw
POSITION_ATTRS = {"x", "y", "width", "height", "name", "view"}


class Widget():
    type_name = None # name used in layouts, defaults to the class name in snake_case

    # Sizes of the content (not counting the border): 5 or "5" exactly,
    # "5+" at least 5, "5-10" between, None for any size
    preferred_width = None
    preferred_height = None
    border = False # drawn by the view; {b} / {nb} in the layout overrides this
    title = None   # shown in the border, defaults to the widget's name
    focusable = False     # can be focused with Tab or a click, and then gets key presses
    captures_text = False # when focused, typed characters go to it before key bindings

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        name = cls.__dict__.get("type_name") or re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__).lower()
        WIDGET_TYPES[name] = cls

    def __init__(self):
        self._ready = False # attribute changes only redraw once init() is done
        self._dirty = True
        self._canvas = None # last drawn content
        # Where the widget is on screen. The view sets these from the layout;
        # set them in init() for widgets added with view.add()
        self.x = 0
        self.y = 0
        self.width = 0
        self.height = 0
        self.name = None # set by the view for layout widgets
        self.view = None
        self.init()
        self._ready = True

    def __setattr__(self, key, value):
        # Changing any public attribute redraws the widget, so `button.text = "Go"` just works.
        # Mutating a list in place (self.items.append) doesn't, call self.refresh() for that.
        object.__setattr__(self, key, value)
        if key.startswith("_") or not self.__dict__.get("_ready") or key in POSITION_ATTRS:
            return
        if key in LAYOUT_ATTRS:
            if self.view: self.view.relayout()
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
        """True if the mouse is inside this widget."""
        x, y = self.mouse_pos()
        return 0 <= x < self.width and 0 <= y < self.height

    # --- Override these ---
    def init(self): pass             # set up attributes; the size isn't known yet
    def draw(self, c:Canvas): pass   # draw into c, which is exactly width x height
    def on_input(self, input:Input): pass # key inputs only arrive while focused
    def on_resize(self): pass        # called after x, y, width, height change
    def on_focus(self): pass
    def on_blur(self): pass


def _call(callback, *args):
    if callback: callback(*args)


class Text(Widget):
    """Text that wraps to fit. align is "left", "center" or "right"."""
    def init(self):
        self.text = ""
        self.align = "left"
        self.style = ""
    def draw(self, c):
        pad = {"left": pad_right, "center": pad_center, "right": pad_left}[self.align]
        for i, line in enumerate(wrap(str(self.text), c.width)[:c.height]):
            c.text(0, i, pad(line, c.width), self.style or self.theme("text"))


class Label(Text):
    """One line of text, cut off with … if too long."""
    preferred_height = 1
    def draw(self, c):
        pad = {"left": pad_right, "center": pad_center, "right": pad_left}[self.align]
        c.text(0, c.height // 2, pad(str(self.text), c.width), self.style or self.theme("text"))


class Button(Widget):
    preferred_width = "5+"
    preferred_height = 1
    focusable = True
    def init(self):
        self.text = "Button"
        self.hovered = False
        self.callback = None
    def on_click(self, callback):
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


class TextInput(Widget):
    """A one-line text box. Click or Tab to it, then type."""
    preferred_width = "5+"
    preferred_height = 1
    border = True
    focusable = True
    captures_text = True
    def init(self):
        self.value = ""
        self.placeholder = ""
        self.cursor = 0 # index in value
        self.scroll = 0 # first visible character, when the value is longer than the box
        self.submit_callback = None
        self.change_callback = None
    def on_submit(self, callback): # called with the value when Enter is pressed
        self.submit_callback = callback
    def on_change(self, callback): # called with the value after every edit
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


class ProgressBar(Widget):
    preferred_height = 1
    def init(self):
        self.value = 0.0 # 0 to 1
        self.show_percent = True
    def draw(self, c):
        value = max(0.0, min(1.0, float(self.value)))
        label = f" {round(value * 100):>3}%" if self.show_percent else ""
        bar = max(0, c.width - len(label))
        filled = round(value * bar)
        mid = c.height // 2
        c.text(0, mid, "█" * filled, self.theme("progress"))
        c.text(filled, mid, "░" * (bar - filled), self.theme("progress_empty"))
        c.text(bar, mid, label)


class Checkbox(Widget):
    preferred_width = "5+"
    preferred_height = 1
    focusable = True
    def init(self):
        self.text = ""
        self.checked = False
        self.change_callback = None
    def on_change(self, callback): # called with True/False
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


class Toggle(Checkbox):
    """An on/off switch. Same as Checkbox, drawn differently."""
    def draw(self, c):
        mid = c.height // 2
        x = c.text(0, mid, " ON  " if self.checked else " OFF ", self.theme("on" if self.checked else "off"))
        c.text(x + 1, mid, fit(self.text, c.width - x - 1), self.theme("button_focus") if self.focused else "")


class Menu(Widget):
    """A list to pick from with the arrow keys and Enter, or a click."""
    border = True
    focusable = True
    def init(self):
        self.items = []
        self.selected = 0
        self.scroll = 0
        self.select_callback = None
    def on_select(self, callback): # called with (index, item) on Enter or click
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

    def draw(self, c):
        # Keep the selection in view
        if(self.selected < self.scroll): object.__setattr__(self, "scroll", self.selected)
        if(self.selected >= self.scroll + c.height): object.__setattr__(self, "scroll", self.selected - c.height + 1)
        for row, item in enumerate(self.items[self.scroll:self.scroll + c.height]):
            index = self.scroll + row
            s = ""
            if(index == self.selected):
                s = self.theme("selected" if self.focused else "selected_unfocused")
            c.text(0, row, pad_right(" " + str(item), c.width), s)


class Table(Widget):
    border = True
    def init(self):
        self.columns = [] # header names
        self.rows = []    # lists of values
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


class Stdout(Widget):
    """Shows everything printed (and stderr, in red). Scroll with the mouse wheel."""
    border = True
    preferred_width = "10+"
    preferred_height = "3+"
    def init(self):
        self.lines = [["", ""]] # [text, style]
        self.max_lines = 500
        self.scroll = 0 # wrapped lines up from the bottom
    def on_input(self, input):
        if(input.type in ("stdout", "stderr")):
            s = self.theme("error") if input.type == "stderr" else ""
            # Text can arrive mid-line, so the first part continues the last line
            parts = input.details["text"].split("\n")
            self.lines[-1][0] += parts[0]
            if(parts[0] and s): self.lines[-1][1] = s
            self.lines.extend([part, s] for part in parts[1:])
            del self.lines[:-self.max_lines]
            if(self.scroll): self._set_scroll(self.scroll + len(parts) - 1) # stay put while scrolled up
            self.refresh()
        elif(input.type == "mouse_scroll" and self.mouse_over()):
            step = 1 if input.details["direction"] == "up" else -1
            self._set_scroll(max(0, self.scroll + step))
            self.refresh()
    def _set_scroll(self, value):
        object.__setattr__(self, "scroll", value)
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
