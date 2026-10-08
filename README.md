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

## What's in it

- **Layouts drawn as text**: each word is a grid cell, `-` and `|` stretch a widget
  across cells, and borders between neighbours join up.
- **Widgets**: text, labels, buttons, one-line and multi-line text boxes (with password
  mode and history), checkboxes, toggles, radio buttons, dropdowns, sliders, progress
  bars, menus, folding trees, tables, a calendar and date picker, tabs, a log viewer with
  levels and search, a box that shows everything you print, a terminal that runs a shell
  or any program inside the layout, and a pixel canvas with lines, shapes and curves. Panels group widgets into reusable pieces, and lines between
  widgets can be made draggable.
- **Styled text**: `"[bold red]Error:[/] couldn't open [cyan]notes.txt[/]"` in labels,
  buttons and text.
- **Text boxes that behave**: select with the mouse or Shift, copy, cut and paste,
  pasting in one go, and dim hints before, after and ahead of the cursor for autocomplete.
- **Inline views**: draw in a few rows under the prompt instead of the whole screen, with
  printed text scrolling above.
- **Popups**: dialogs, dropdowns and command menus that float over the layout, and
  questions that wait for the answer: `if view.confirm("Delete it?"): ...`, and
  notifications in the corner: `view.notify("Saved", "ok")`.
- **Mouse and keyboard**: clicks, dragging, the scroll wheel, right-click menus, Tab
  between widgets, your own key bindings, and a footer that shows the keys that work
  right now.
- **Timers**: `view.every(1, tick)` and `view.after(5, fn)`, no threads needed.
- **Themes**: restyle any part, with 73 named colors, the 256-color palette, or exact
  hex colors.
- **Your own widgets**: subclass `Widget`, draw into a canvas, and it works in layouts.

## Documentation

- [Overview](https://github.com/olliez-mods/cmdgui/blob/main/docs/index.md): ways to build a view, changing widgets, timers, running and quitting
- [Layouts](https://github.com/olliez-mods/cmdgui/blob/main/docs/layouts.md)
- [Widgets](https://github.com/olliez-mods/cmdgui/blob/main/docs/widgets.md)
- [Popups](https://github.com/olliez-mods/cmdgui/blob/main/docs/popups.md)
- [Keys and focus](https://github.com/olliez-mods/cmdgui/blob/main/docs/keys-and-focus.md)
- [Themes and colors](https://github.com/olliez-mods/cmdgui/blob/main/docs/themes.md)
- [Your own widgets](https://github.com/olliez-mods/cmdgui/blob/main/docs/custom-widgets.md)

The [examples](https://github.com/olliez-mods/cmdgui/tree/main/examples) folder has a
widget demo, a dashboard, popups, dialogs that wait for an answer, tabs, a console, a
file browser, pixel graphics, a log viewer with draggable lines, date pickers, a shell and
a Python REPL side by side, and an inline progress display.
