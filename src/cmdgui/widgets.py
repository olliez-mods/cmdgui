import re
from .shorts import *
from .inputs import Input, mouse

# Type name -> widget class, for layout strings. Filled in automatically.
WIDGET_TYPES = {}

class Widget():
    type_name = None # name used in layouts, defaults to the class name in snake_case

    # Sizes of the content (not counting the border): 5 or "5" exactly,
    # "5+" at least 5, "5-10" between, None for any size
    preferred_width = None
    preferred_height = None
    border = False # drawn by the view; {b} / {nb} in the layout overrides this
    title = None   # shown in the border, defaults to the widget's name

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        name = cls.__dict__.get("type_name") or re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__).lower()
        WIDGET_TYPES[name] = cls

    def __init__(self):
        # Where the widget is on screen. The view sets these from the layout;
        # set them in init() for widgets added with view.add()
        self.x = 0
        self.y = 0
        self.width = 0
        self.height = 0
        self.name = None # set by the view for layout widgets
        self.view = None
        self.super_init()

    def mouse_pos(self):
        """Mouse position relative to this widget's top-left corner."""
        return mouse.x - self.x, mouse.y - self.y

    def mouse_over(self):
        """True if the mouse is inside this widget."""
        x, y = self.mouse_pos()
        return 0 <= x < self.width and 0 <= y < self.height

    def refresh(self):
        """Redraw now. Use after changing a widget from your own code."""
        if self.view:
            with self.view.lock:
                self.super_draw()
        else:
            self.super_draw()

    def super_init(self):
        self.init()
    def super_draw(self):
        if self.view and self.view.too_small: return # the view is showing "terminal too small"
        self.draw()
    def super_on_input(self, input:Input):
        self.on_input(input)
    def super_on_resize(self):
        self.on_resize()

    def init(self): pass
    def draw(self): pass
    def on_input(self, input:Input): pass
    def on_resize(self): pass # called after x, y, width, height change

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

        self.super_draw()
    def draw(self):
        c = Canvas(self.width, self.height)
        for key, _ in self.tiles.items():
            x,y = key
            c.put(x, y, "#")
        x, y = self.mouse_pos()
        c.put(x, y, "X" if mouse.is_down() else "O")
        c.draw_to(self.x, self.y)

class Stdout(Widget):
    border = True
    preferred_width = "10+"
    preferred_height = "3+"
    def init(self):
        self.lines = [""]
        self.max_lines = 500
    def on_input(self, input):
        if(input.type == "stdout"):
            # Text can arrive mid-line, so the first part continues the last line
            parts = input.details["text"].split("\n")
            self.lines[-1] += parts[0]
            self.lines.extend(parts[1:])
            del self.lines[:-self.max_lines]
            self.super_draw()
    def draw(self):
        c = Canvas(self.width, self.height)
        lines = self.lines[:-1] if self.lines[-1] == "" else self.lines # skip empty line after a trailing \n
        wrapped = [part for line in lines for part in wrap(line, self.width)]
        for i, line in enumerate(wrapped[-self.height:]):
            c.text(0, i, line)
        c.draw_to(self.x, self.y)

class Button(Widget):
    preferred_width = "5+"
    preferred_height = 1
    def init(self):
        self.text = "Button"
        self.hovered = False
        self.callback = None
    def on_click(self, callback):
        self.callback = callback
    def on_input(self, input):
        if(not input.type.startswith("mouse")): return

        if(self.mouse_over() != self.hovered):
            self.hovered = self.mouse_over()
            self.super_draw()

        if(input.type == "mouse_down" and self.hovered and self.callback):
            self.callback()

    def draw(self):
        c = Canvas(self.width, self.height)
        mid = self.height // 2 # vertically centred
        c.text(0, mid, pad_center(self.text, self.width, "*" if self.hovered else " "))
        c.put(0, mid, "[")
        c.put(self.width - 1, mid, "]")
        c.draw_to(self.x, self.y)

