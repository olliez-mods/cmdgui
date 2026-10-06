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
from cmdgui import View
import time

view = View("""
    button[start]  button[pause]  .
    stdout[log]    -              -
""")

view.start.text = "Start"
view.start.on_click(lambda: print("started"))
view.pause.text = "Pause"
view.pause.on_click(lambda: print("paused"))

for i in range(100):
    print(f"tick {i}")   # shows up in the log box
    time.sleep(0.5)
```

Press `q` to quit (or Ctrl+C).

## Layouts

Each word is a grid cell. Write `type[name]` to create a widget:

| Token | Meaning |
|---|---|
| `button[start]` | a `button` widget named `start` |
| `stdout` | a widget whose name is its type |
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

Setting an attribute redraws the widget: `view.bar.value = 0.5` just works.
If you change a list in place (`view.menu.items.append(...)`), call `widget.refresh()`.

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
from cmdgui import Widget, View

class Clock(Widget):
    preferred_height = 1          # 5, "5+" (at least), "5-10" (between), or None
    border = True

    def init(self):
        self.time = ""

    def draw(self, c):            # c is a Canvas exactly the widget's size
        c.text(0, 0, self.time)

    def on_input(self, input):    # mouse, stdout, and keys (while focused)
        pass

view = View("clock")              # registered automatically as "clock"
```

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
