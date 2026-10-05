from .shorts import *
from .inputs import Input, mouse

class Widget():
    def __init__(self):
        # Where the widget is on screen, set these in init()
        self.x = 0
        self.y = 0
        self.width = 0
        self.height = 0
        self.super_init()

    def mouse_pos(self):
        """Mouse position relative to this widget's top-left corner."""
        return mouse.x - self.x, mouse.y - self.y

    def mouse_over(self):
        """True if the mouse is inside this widget."""
        x, y = self.mouse_pos()
        return 0 <= x < self.width and 0 <= y < self.height

    def super_init(self):
        self.init()
    def super_draw(self):
        self.draw()
    def super_on_input(self, input:Input):
        self.on_input(input)

    def init(self): pass
    def draw(self): pass
    def on_input(self, input:Input): pass

class DrawMouse(Widget):
    def init(self):
        self.x = 1 # where the canvas is drawn on screen
        self.y = 1
        self.width = 10
        self.height = 10
        self.tiles:dict[tuple[int,int], bool] = {}
    def on_input(self, input):
        if(not input.type.startswith("mouse")): return

        # Toggle a tile on click, and on each new cell while dragging
        if(input.type == "mouse_down" or (mouse.is_down() and mouse.moved)):
            pos = self.mouse_pos()
            if(self.tiles.get(pos)): self.tiles.pop(pos)
            else: self.tiles[pos] = True

        self.super_draw()
    def draw(self):
        c = Canvas(self.width, self.height)
        c.border()
        for key, _ in self.tiles.items():
            x,y = key
            c.put(x, y, "#")
        x, y = self.mouse_pos()
        c.put(x, y, "X" if mouse.is_down() else "O")
        c.draw_to(self.x, self.y)

class Stdout(Widget):
    def init(self):
        self.x = 12 # where the canvas is drawn on screen
        self.y = 1
        self.width = 40
        self.height = 10
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
        c.border(title="stdout")
        inner_w, inner_h = self.width - 2, self.height - 2
        lines = self.lines[:-1] if self.lines[-1] == "" else self.lines # skip empty line after a trailing \n
        wrapped = [part for line in lines for part in wrap(line, inner_w)]
        for i, line in enumerate(wrapped[-inner_h:]):
            c.text(1, 1 + i, line)
        c.draw_to(self.x, self.y)

class Button(Widget):
    def init(self):
        self.x = 60
        self.y = 5
        self.width = 10
        self.hovered = False
    def on_input(self, input):
        if(mouse.moved):
            if(mouse.x >= self.x and mouse.x < self.x + self.width and
               mouse.y == self.y):
                self.hovered = True
            else:
                self.hovered = False

        if(mouse.moved):
            self.super_draw()

        if(input.type == "mouse_down" and self.hovered):
            print("CLICK")

    def draw(self):
        c = Canvas(self.width, 1)
        c.text(0, 0, pad_center("Butt", self.width, "*" if self.hovered else " "))
        c.put(0, 0, "[")
        c.put(self.width - 1, 0, "]")
        c.draw_to(self.x, self.y)

