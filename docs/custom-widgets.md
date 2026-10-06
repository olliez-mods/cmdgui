# Your own widgets

Subclass `Widget`, and override `draw` and (if it takes input) `on_input`. Here's a
counter you change with the arrow keys or the mouse wheel:

```python
from cmdgui import View, Widget, field

class Counter(Widget):
    value: int = field(default=0, kw_only=False)  # fields become constructor arguments
    step: int = 1

    preferred_height = 1          # sizes: 5, "5+" (at least), "5-10" (between), or None
    focusable = True              # Tab and clicks can focus it, then it gets key presses

    def on_input(self, input):
        if input.type == "key":
            if input.details["key"] in ("up", "right", "+"): self.value += self.step
            if input.details["key"] in ("down", "left", "-"): self.value -= self.step
        elif input.type == "mouse_scroll" and self.mouse_over():
            self.value += self.step if input.details["direction"] == "up" else -self.step

    def draw(self, c):            # c is a Canvas exactly the widget's size
        s = self.theme("button_focus") if self.focused else ""
        c.text(0, c.height // 2, f"◀ {self.value} ▶", s)

    def content_size(self):       # the size the content wants, for popups
        return len(f"◀ {self.value} ▶"), 1

view = View("counter[apples] counter[pears]")   # registered automatically as "counter"
view.apples.step = 5
view = View("count", count=Counter(10, step=2))
```

Setting `self.value` redraws the widget by itself, and `enabled=False` works without
any extra code.

## Fields

Annotated class attributes are fields: they become constructor arguments, and editors
autocomplete and type-check them like a dataclass.

```python
from typing import Callable, Optional

class Clock(Widget):
    time: str = field(default="", kw_only=False)  # can also be passed positionally
    show_seconds: bool = True                      # keyword-only, the default
    history: list = field(default_factory=list)    # a fresh list for each clock
    callback: Optional[Callable] = field(default=None, alias="on_tick")  # passed as on_tick=
```

Setting any field (or any other public attribute) redraws the widget. Attributes
starting with `_` don't. Mutating a list in place doesn't either: call `self.refresh()`.

To change an inherited default, just assign it: `border = True`.

## Class settings

These are plain class attributes, not constructor arguments:

| | |
|---|---|
| `type_name` | the name used in layouts; defaults to the class name in snake_case |
| `focusable` | can be focused with Tab or a click, and then gets key presses |
| `captures_text` | when focused, typed characters go to it before key bindings (text boxes) |

## Methods to override

| | |
|---|---|
| `init()` | set up other attributes. Runs before constructor arguments are applied, and before the size is known |
| `draw(c)` | draw into the canvas `c`, which is exactly `width` x `height` |
| `on_input(input)` | handle an input, see below |
| `content_size()` | `(width, height)` the content would like, `None` for either if it doesn't matter. Popups use it to size themselves |
| `on_resize()` | called after `x`, `y`, `width` or `height` change |
| `on_focus()`, `on_blur()` | called when it gains or loses focus |

## Inputs

`input.type` says what happened, and `input.details` has the rest:

| Type | Details | Sent to |
|---|---|---|
| `key` | `key` (the key name), `char` (the typed character, or `None`) | the focused widget |
| `mouse_down`, `mouse_up` | `x`, `y`, `button` (0 left, 1 middle, 2 right) | every enabled widget |
| `mouse_move` | `x`, `y`, and `button` while dragging | every enabled widget |
| `mouse_scroll` | `x`, `y`, `direction` (`"up"` or `"down"`) | every enabled widget |
| `stdout`, `stderr` | `text` | every widget |

Mouse inputs go to every widget, so check `self.mouse_over()` before reacting to one.
Positions in `details` are screen positions; `self.mouse_pos()` gives the mouse relative
to the widget. `mouse` (from `cmdgui`) has the mouse state: `mouse.is_down(button)` and
`mouse.moved`. See [Keys and focus](keys-and-focus.md) for key names.

## Drawing

`Canvas` methods:

| | |
|---|---|
| `c.put(x, y, char, style)` | one character |
| `c.text(x, y, text, style)` | a string, clipped at the edge. Returns the x just after it |
| `c.fill(x, y, w, h, char, style)` | fill a rectangle, the whole canvas by default |
| `c.border(x, y, w, h, kind, style, title)` | a box; `kind` is `single`, `double`, `rounded`, `heavy` or `ascii` |
| `c.restyle(style)` | give every cell the same style |

Wide characters (emoji, CJK) take two cells and are handled for you. Styles come from
`style()` or, better, from the theme: `self.theme("dim")` lets users restyle your widget.
A widget can use its own theme keys too; `self.theme()` returns no style for a key the
theme doesn't have.

`cmdgui.shorts` has text helpers that understand wide characters: `text_width`,
`fit(text, width)` (cuts it off with `…`), `wrap(text, width)`, and `pad_left`,
`pad_right`, `pad_center`.

## Other things a widget can use

- `self.view`: the view showing it, or `None`
- `self.focused`, `self.can_focus`
- `self.x`, `self.y`, `self.width`, `self.height`: where it is on screen
- `self.refresh()`: redraw on the next frame, from any thread
- `self.copy()`: a separate copy, not attached to any view
