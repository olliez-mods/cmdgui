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

## Panels in a layout

A `Panel` is a widget that holds a layout of other widgets, written like a view. It goes
in a layout cell like any widget, to group widgets that belong together:

```python
class Sidebar(Panel):
    layout = """
        search
        results
    """
    search = TextInput()
    results = Menu()

class App(View):
    layout = "sidebar{+b} editor{+b}"
    sidebar = Sidebar()
    editor = TextArea()

view = App()
view.sidebar.search    # typed in your editor
```

`view.sidebar` is the panel itself, and like any widget it has `border`, `title`,
`visible`, `enabled` and the rest, as arguments (`Sidebar(border=True)`), attributes or
flags on its cell (`{+b}`, `{w=30}`, `{t=title}`). Hiding or disabling a panel hides or
disables everything in it. Bordered widgets inside join up with its border, and their
titles go on it, so a panel's border only shows a title if you give it one. A panel is
also how a whole group of widgets can be one side of a [draggable line](#draggable-lines).

Panels also go in [tabs](widgets.md#tabs), and [popups](popups.md) are panels that float.

## Scrolling panels

A panel with `scrollable=True`, or `{+s}` on its cell, can be shorter than its widgets
need, and scrolls:

```python
class App(View):
    layout = """
        form{+b,+s}  log{+b}
    """
    form = LongForm()    # a Panel with more rows than fit
    log = Stdout()
```

- It asks the layout for no particular height, so it takes what's left over. When its
  widgets need more, they're laid out at their full height and the panel shows part of
  them, with a scroll bar in its last column showing where you are.
- The mouse wheel over it scrolls it, unless what's under the mouse scrolls by itself (a
  list, a log, a text area, Markdown): that gets the wheel, as in a browser.
- When a widget inside gets focus (Tab, or a click), it scrolls so that widget shows.
- Widgets cut off at its edges are cut off properly: they draw, get clicks and have
  borders only where they show. Borders inside still join the panel's own.
- `panel.scroll` is how far down it is, in rows; `panel.scroll_by(rows)` scrolls from
  code. It only scrolls up and down.
- `{+s}` is for panels; to scroll a single widget that doesn't scroll by itself, put it in
  one: `Panel(widget, scrollable=True)`.

See `examples/scrolling.py`.

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
| `+s` | `scrollable` | a [panel](#scrolling-panels) scrolls when it's shorter than its widgets need |
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
rounded, single, ascii). Panels, `Tabs` and popups take `border_style` like any widget;
a tab's border takes its `Tabs`' style unless the tab has its own.

## Draggable lines

`adjustable()` puts a line between two widgets that are next to each other, for
dragging with the mouse:

```python
class App(View):
    layout = """
        heading   heading
        files     editor
        files     log
    """
    heading = Label("my editor")
    files = Tree(...)
    editor = TextArea()
    log = Log()

view = App()
view.adjustable(view.files, [view.editor, view.log], position=24)  # drag left and right
view.adjustable(view.editor, view.log, position=-6)                # drag up and down
```

Dragging only moves room between the two sides of the line. Everything else stays put,
so `heading` keeps its full width however far you drag.

- The two sides have to line up: side by side with the same rows, or one above the
  other with the same columns. Together they form a rectangle, and the line moves
  inside it. If they don't line up, `adjustable()` raises an error that says why.
- A side can be a list of widgets stacked along the line, like `[view.editor, view.log]`
  above. Each one has to reach from the line to the side's far edge. For anything more
  complicated, put the widgets in a [panel](#panels-in-a-layout): the panel is one
  widget on its side, and its own layout shares out the room.
- The line is always drawn, even between widgets without borders. It has a grip, and
  lights up under the mouse (`divider_hover` in the theme).
- Each side keeps its minimum size. A widget's width (`w=24` or `preferred_width`) is
  only where the line starts.
- Moving one line doesn't move another. Above, dragging the `files` line changes the
  width of `editor` and `log`, but not the height they share.
- Panels and popups have `adjustable()` too. Call it in their `init()`.

### Position

`position` says where the line goes, for the side you name first:

| `position` | |
|---|---|
| `0.3` (a float) | that fraction of the room |
| `30` (an int) | 30 cells |
| `-30` (a negative int) | the other side gets 30 cells, and this one the rest |

Without one, the line starts where the layout puts it. Whatever kind you pick stays the
same as the terminal resizes, and when the line is dragged: `-30` keeps the other side
30 cells wide, a fraction stays a fraction.

`adjustable()` returns an `Edge`. Get it again later with `edge()`, naming one widget
from each side:

```python
view.adjustable(view.files, [view.editor, view.log], on_change=save_width)
view.edge(view.files, view.editor).position = 0.3   # files get 30%
view.edge(view.editor, view.files).position         # 0.7: for the side named first
```

`on_change(position)` is called when the user drags the line, with the position for
the side named first, and in the same kind of number. `edge.on_change(fn)` sets it
later, and `None` stops it.

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
