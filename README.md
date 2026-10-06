# cmdgui

Simple terminal GUIs in Python. Draw your layout as text, fill in the widgets,
and keep writing your program — the view runs on its own thread, so there's no
event loop to hand control to and no draw calls to make.

```
┌─ name ───────────────────┐
│quinn                     │[         Greet          ] ON   fast
├─ fruit ──────────────────┼─ scores ──────────────────────────────────┐
│ apple                    │name      score  city                      │
│ banana                   │Ada       98     London                    │
│ cherry                   │Linus     87     Helsinki                  │
│                          ├─ log ─────────────────────────────────────┤
│                          │Hello, quinn! 👋                           │
│                          │picked cherry                              │
└──────────────────────────┴───────────────────────────────────────────┘
 ████████████████████████████████░░░░░░░░░░░░░░░░  67%[ ] done
```

No dependencies. macOS and Linux; Windows support is written but untested.

## Install

```bash
pip install cmdgui
```

## Quick start

```python
from cmdgui import View, Button, Stdout
import time

class App(View):
    layout = """
        start  pause  .
        log    -      -
    """
    start = Button("Start", on_click=lambda: print("started"))
    pause = Button("Pause", on_click=lambda: print("paused"))
    log = Stdout()

view = App()

for i in range(100):
    print(f"tick {i}")   # shows up in the log box
    time.sleep(0.5)
```

Press `q` to quit (or Ctrl+C). Because the widgets are class attributes, your
editor knows `view.start` is a `Button` — autocomplete and type checking work.

### Three ways to build a view

They can be mixed freely:

```python
from cmdgui import View, Label

# 1. A subclass: everything in one place, fully typed in your editor
class App(View):
    layout = "heading \n stdout"
    heading = Label("Hello", align="center")
view = App()

# 2. Widgets passed in: quick one-off views
view = View("heading \n stdout", heading=Label("Hello", align="center"))

# 3. Types in the layout, configured afterwards
view = View("label[heading] \n stdout")
view.heading.set(text="Hello", align="center")
```

A keyword argument overrides a subclass's widget of the same name. Each view made
from a subclass gets its own copies of the widgets. For typed access to widgets
declared in the layout string, use `view.get("heading", Label)`.

## Layouts

Each word is a grid cell. Write `type[name]` to create a widget:

| Token | Meaning |
|---|---|
| `button[start]` | a `button` widget named `start` |
| `heading` | the widget you passed in (or declared on the class) as `heading` |
| `stdout` | otherwise: a widget whose name is its type |
| `start` | the existing widget `start` again — it spans into this cell |
| `-` | same as the cell to the left |
| `\|` | same as the cell above |
| `.` | empty cell |
| `{b}` / `{nb}` | on the first cell of a widget: force a border on / off |

Every widget has to cover a rectangle. Get widgets with `view.start` or `view["start"]`.

**Sizes** come from the widgets: a button wants to be 1 line tall, so its row is
1 line tall; everything else shares the remaining space. If the terminal is too
small for the layout's minimum size, the view shows a message until it's resized.

**Borders** are drawn by the view, and neighbours share a single line with the
right junctions (`├ ┬ ┼`). The border title is the widget's name, or its `title`.
The focused widget's border is highlighted.

## Widgets

| Type | Class | What it does |
|---|---|---|
| `text` | `Text` | Wrapped text. `text`, `align` (`left`/`center`/`right`) |
| `label` | `Label` | One line of text |
| `button` | `Button` | `text`, `on_click(fn)`. Click, or Enter/Space when focused |
| `text_input` | `TextInput` | `value`, `placeholder`, `on_submit(fn)`, `on_change(fn)` |
| `progress_bar` | `ProgressBar` | `value` from 0 to 1 |
| `checkbox` | `Checkbox` | `text`, `checked`, `on_change(fn)` |
| `toggle` | `Toggle` | An on/off switch, same API as `Checkbox` |
| `menu` | `Menu` | `items`, `selected`, `on_select(fn(index, item))` |
| `table` | `Table` | `columns`, `rows`. Scroll with the mouse wheel |
| `stdout` | `Stdout` | Everything printed, stderr in red. Scroll with the mouse wheel |

Every widget also takes `border`, `title`, `preferred_width` and `preferred_height`.
The first positional argument is the main content: `Label("text")`, `Menu(items)`,
`Table(columns)`, `ProgressBar(0.5)`. Callbacks can be passed in (`on_click=`) or set
later (`button.on_click(fn)`).

Setting an attribute redraws the widget: `view.bar.value = 0.5` just works, and
`widget.set(text=..., align=...)` changes several at once. If you change a list in
place (`view.menu.items.append(...)`), call `widget.refresh()`.

## Keys and focus

- **Tab** / **Shift+Tab** or a click moves focus between widgets that take input.
- Key presses go to the focused widget; typed characters go to a focused text box first.
- `view.on_key("ctrl+s", save)` binds a key. Key names: letters, `enter`, `escape`,
  `tab`, `backspace`, `delete`, `up`/`down`/`left`/`right`, `home`/`end`,
  `page_up`/`page_down`, `ctrl+a`, `alt+x`, `ctrl+up`, ...
- `View(layout, quit_key="q")` sets the quit key; `quit_key=None` turns it off.

## Ending the program

```python
with View("...") as view:
    ...
    view.wait()   # blocks until q, view.quit() or Ctrl+C
```

Without `wait()`, the quit key ends your program as if it had finished.
If anything raises — in your code or inside a callback — the terminal is put back
to normal first, so the traceback is visible.

## Your own widgets

```python
from cmdgui import Widget, View, field

class Clock(Widget):
    time: str = field(default="", kw_only=False)  # fields become constructor arguments
    show_seconds: bool = True
    history: list = field(default_factory=list)   # a fresh list for each clock

    preferred_height = 1          # 5, "5+" (at least), "5-10" (between), or None
    border = True

    def init(self):               # other setup (not constructor arguments)
        self.ticks = 0

    def draw(self, c):            # c is a Canvas exactly the widget's size
        c.text(0, 0, self.time)

    def on_input(self, input):    # mouse, stdout, and keys (while focused)
        pass

view = View("clock")              # registered automatically as "clock"
view = View("now", now=Clock("12:00"))
```

Annotated attributes are fields: keyword arguments by default, positional with
`field(kw_only=False)`. Editors autocomplete and type-check them like a dataclass.

`Canvas` has `put`, `text`, `fill` and `border`; `self.mouse_pos()` and
`self.mouse_over()` give the mouse relative to the widget; `self.theme("key")`
gets a style from the theme.

## Themes

```python
from cmdgui import View, style

view = View("...", theme={
    "border_focus": style(fg="magenta", bold=True),
    "selected": style(fg="black", bg="yellow"),
})
```

See `DEFAULT_THEME` in `cmdgui.widgets` for every key.
