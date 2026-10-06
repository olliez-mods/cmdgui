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
| `{b}` / `{nb}` | on the first cell of a widget: force a border on / off |

Every widget has to cover a rectangle. Get widgets with `view.start` or `view["start"]`.
The type names are the class names in snake_case: `text_input`, `progress_bar`,
`radio_group` and so on. See [Widgets](widgets.md) for the full list. Your own widget
classes are registered the same way, see [Your own widgets](custom-widgets.md).

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
`{b}` / `{nb}` in the layout.
