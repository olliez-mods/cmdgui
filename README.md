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
| `text_area` | `TextArea` | Multi-line text box, long lines wrap. `value`, `placeholder`, `on_change(fn)` |
| `progress_bar` | `ProgressBar` | `value` from 0 to 1 |
| `slider` | `Slider` | `value`, `min`, `max`, `step`, `show_value`, `on_change(fn)`. Drag, click, or arrow keys |
| `checkbox` | `Checkbox` | `text`, `checked`, `on_change(fn)` |
| `toggle` | `Toggle` | An on/off switch, same API as `Checkbox` |
| `radio_group` | `RadioGroup` | `options`, `selected`, `value`, `horizontal`, `on_change(fn(index, option))` |
| `menu` | `Menu` | `items`, `selected`, `on_select(fn(index, item))` |
| `tree` | `Tree` | Nested items that fold open. `nodes`, `selected` (a path of labels), `on_select(fn(path))`, `expand()`, `collapse()`, `expand_all()`. See below |
| `table` | `Table` | `columns`, `rows`. Scroll with the mouse wheel |
| `stdout` | `Stdout` | Everything printed, stderr in red. Scroll with the mouse wheel. `clear()`, and `print(...)` / `write(text)` to show text in this box only |

Every widget also takes `border`, `title`, `preferred_width`, `preferred_height` and
`enabled`. A widget with `enabled=False` is greyed out, can't be focused, and ignores
clicks and keys; `view.save.enabled = False` turns one off while the program runs.
The first positional argument is the main content: `Label("text")`, `Menu(items)`,
`Table(columns)`, `ProgressBar(0.5)`. Callbacks can be passed in (`on_click=`) or set
later (`button.on_click(fn)`).

Setting an attribute redraws the widget: `view.bar.value = 0.5` just works, and
`widget.set(text=..., align=...)` changes several at once. If you change a list in
place (`view.menu.items.append(...)`), call `widget.refresh()`.

### Trees

`nodes` is a dict of label → children. Children are another dict, a list, `None` for
a leaf, or a function that returns them, called the first time the node is opened:

```python
import os
from cmdgui import Tree

def folder(path):
    return lambda: {name: folder(os.path.join(path, name)) if os.path.isdir(os.path.join(path, name)) else None
                    for name in sorted(os.listdir(path))}

files = Tree({"src": {"main.py": None, "util.py": None}, "docs": ["intro.md", "api.md"]})
browser = Tree(folder("."), on_select=lambda path: print(os.path.join(*path)))
```

A node is picked out by its path, a tuple of labels like `("src", "main.py")`. Use the
arrow keys (right opens, left closes or goes to the parent), Enter, or click. After the
data behind a function node changes, call `tree.reload()`.

## Popups

A popup floats over the layout. It has its own layout and widgets, just like a view,
and sizes itself to fit them:

```python
from cmdgui import View, Popup, Label, Button, Stdout

class Confirm(Popup):
    layout = """
        message  -
        yes      no
    """
    title = "Clear the log?"
    message = Label("This can't be undone.")
    yes = Button("Clear")
    no = Button("Cancel")

    def init(self):                    # wire up the popup's own widgets
        self.no.on_click(self.close)

class App(View):
    layout = "clear \n log"
    clear = Button("Clear log", on_click=lambda: view.show(view.confirm))
    log = Stdout()
    confirm = Confirm()                # popups can live on the view too

view = App()
view.confirm.yes.on_click(lambda: (view.log.clear(), view.confirm.close()))
```

- `view.show(popup)` opens it in the middle, or use `below=widget`, `above=widget` or
  `at=(x, y)`. It flips to the other side if there's no room.
- `popup.close()`, `popup.is_open`, `popup.on_close(fn)`.
- `view.alert("Saved!", title="Done")` shows a message with an OK button.
- A popup with one widget doesn't need a layout: `Popup(Menu(items))`, or a subclass
  with a single widget.

Settings, as class attributes or constructor arguments:

| Setting | Default | |
|---|---|---|
| `modal` | `True` | blocks clicks and focus for everything underneath |
| `close_on_escape` | `True` | |
| `close_on_outside_click` | `False` | for a modal popup the click just closes it; otherwise it goes through too |
| `keep_typing` | `False` | the focused text box keeps getting typed text, while arrows and Enter go to the popup (autocomplete, command menus) |
| `border`, `title` | `True`, `None` | |
| `width`, `height` | `None` | outer size; `None` fits the content |

Inside a popup, a widget's border title is only shown if you set its `title`.
`examples/simple_console.py` has a `/` command menu and `examples/popups.py` has a dialog and a dropdown.

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

Override `content_size()` to return the `(width, height)` your content wants, so
popups can size themselves around it (`None` for either means "don't care").

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

Colors for `fg` and `bg` can be:

- a basic color, which follows the terminal's theme: `black`, `red`, `green`, `yellow`,
  `blue`, `magenta`, `cyan`, `white`, each also as `bright_red` and so on
- one of 57 more named colors from the 256-color palette: `orange`, `gold`, `teal`,
  `lavender`, `crimson`, `gray`... (see `EXTRA_COLORS` in `cmdgui.shorts`)
- a 256-color palette number: `style(fg=208)`
- an exact color, on terminals with true color: `style(fg="#ff8800")` or `style(fg=(255, 136, 0))`
