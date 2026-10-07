# Layouts

A layout is a grid drawn as text. Each word is a cell:

```python
from cmdgui import View

view = View("""
    text_input[name]  button[go]
    menu[files]       stdout[log]
    |                 |
""")
```

| Token | Meaning |
|---|---|
| `button[start]` | a `button` widget named `start` |
| `heading` | the widget you passed in (or declared on the class) as `heading` |
| `stdout` | otherwise: a widget whose name is its type |
| `start` | the existing widget `start` again: it spans into this cell |
| `-` | same as the cell to the left |
| `\|` | same as the cell above |
| `.` | empty cell |
| `{...}` | on the first cell of a widget: [flags](#flags), like `log{+b,h=5+}` |

Every widget has to cover a rectangle. Get widgets with `view.start` or `view["start"]`.
The type names are the class names in snake_case: `text_input`, `progress_bar`,
`radio_group` and so on. See [Widgets](widgets.md) for the full list. Your own widget
classes are registered the same way, see [Your own widgets](custom-widgets.md).

## No layout

Leave the layout out, and the widgets go one above the other, in the order they're
declared (class attributes first, then keyword arguments). This works for views,
panels and popups:

```python
class Sidebar(Panel):    # the same as layout = "search \n results"
    search = TextInput()
    results = Menu()
```

## Flags

Put flags in `{}` on the end of a widget's first cell, separated by commas (no spaces,
since spaces separate the cells). They set the widget's attributes, so the layout can
say how big things are and how they look:

```python
layout = """
    files{+b,w=24}   editor{b=rounded}
    |                log{-b,h=6,t=output}
    search{-f}       status{-v}
"""
```

| Flag | Sets | |
|---|---|---|
| `+b` / `-b` | `border` | border on / off |
| `b=rounded` | `border`, `border_style` | a border in a [style](#border-styles): `single`, `rounded`, `heavy`, `double` or `ascii` |
| `w=24`, `w=24+`, `w=20-40` | `preferred_width` | width: exactly, at least, between (see [sizes](#sizes)) |
| `h=6`, `h=6+`, `h=3-8` | `preferred_height` | height |
| `+v` / `-v` | `visible` | shown / [hidden](#hiding-widgets) |
| `+e` / `-e` | `enabled` | enabled / disabled (greyed out) |
| `+f` / `-f` | `tab_stop` | in Tab order / skipped by Tab (a click still focuses it) |
| `t=my_title` | `title` | the border title; `_` shows as a space |

Flags win over the widget's own settings, and they're ordinary attributes afterwards:
`view.status.visible = True` shows a widget the layout hid. A mistake, like an unknown
flag or a bad size, raises a `LayoutError` saying which cell it's in.

## Sizes

Sizes come from the widgets: a button wants to be 1 line tall, so its row is 1 line
tall; everything else shares the remaining space. Change a widget's wishes with
`preferred_width` and `preferred_height`:

| Value | Meaning |
|---|---|
| `5` or `"5"` | exactly 5 |
| `"5+"` | at least 5 |
| `"5-10"` | between 5 and 10 |
| `None` | any size |

These are the size of the content, not counting the border. If the terminal is too
small for the layout's minimum size, the view shows a message until it's resized.

## Borders

Borders are drawn by the view, and neighbours share a single line with the right
junctions (`├ ┬ ┼`). The border title is the widget's name, or its `title`. The
focused widget's border is highlighted.

Some widgets have a border by default (text boxes, menus, tables, stdout) and some
don't (buttons, labels, checkboxes). Change it with `border=True` / `border=False`, or
`{+b}` / `{-b}` in the layout.

### Border styles

| Style | |
|---|---|
| `single` (default) | `┌─┬─┐` |
| `rounded` | `╭─┬─╮`, rounded at the outside corners |
| `heavy` | `┏━┳━┓` |
| `double` | `╔═╦═╗` |
| `ascii` | `+-+-+`, for terminals and fonts without line characters |

Set one for the whole view with `View(border_style="rounded")`, or per widget with
`border_style=` or `{b=heavy}` in the layout. Lines of different styles still join up:
where they meet, the junction takes the style that ranks highest (double, then heavy,
rounded, single, ascii). A panel inside a `Split` or `Tabs`, or a `Popup`, can have its
own `border_style` too; otherwise a panel's border takes its container's style.

## Hiding widgets

`view.status.visible = False` hides a widget (or `-v` in the layout), and `True` shows
it again. A hidden widget isn't drawn, doesn't get clicks or keys, and Tab skips it, but
it keeps everything else: a hidden `Stdout` still collects what's printed.

The layout closes up around it: the rows and columns it was in take no space, and the
borders either side become one line. A widget spanning those rows or columns just gets
smaller. The exception is a row or column a shown widget has no other room in: that one
stays, and the hidden widget's cells are left empty.

So to have neighbours take a hidden widget's space, give the hidden widget a row (or
column) of its own, like the charts in `examples/dashboard.py`: they're the only widgets
in their row, so hiding them (press `c`) gives their room to the log.

```python
class App(View):
    layout = """
        files  editor
        |      problems{-v,h=6}
    """
    ...

view.on_key("ctrl+j", lambda: view.problems.set(visible=not view.problems.visible))
```
