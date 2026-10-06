# Widgets

| Type | Class | What it does |
|---|---|---|
| `text` | [`Text`](#text-and-label) | Wrapped text |
| `label` | [`Label`](#text-and-label) | One line of text |
| `button` | [`Button`](#button) | Click, or Enter/Space when focused |
| `text_input` | [`TextInput`](#textinput) | A one-line text box |
| `text_area` | [`TextArea`](#textarea) | A multi-line text box |
| `checkbox` | [`Checkbox`](#checkbox-and-toggle) | A box to tick |
| `toggle` | [`Toggle`](#checkbox-and-toggle) | An on/off switch |
| `radio_group` | [`RadioGroup`](#radiogroup) | Pick one of several options |
| `select` | [`Select`](#select) | A dropdown: pick one option from a list that opens |
| `slider` | [`Slider`](#slider) | Pick a number by dragging |
| `progress_bar` | [`ProgressBar`](#progressbar) | A bar from 0 to 1 |
| `menu` | [`Menu`](#menu) | A list to pick from |
| `tree` | [`Tree`](#tree) | Nested items that fold open |
| `table` | [`Table`](#table) | Rows and columns |
| `tabs` | [`Tabs`](#tabs) | Several panels in one place, with a bar to switch between them |
| `stdout` | [`Stdout`](#stdout) | Everything your program prints |
| `graphics` | [`Graphics`](#graphics) | Draw in pixels: lines, shapes, curves |

## Common to every widget

Every widget takes these, as constructor arguments or attributes:

| | |
|---|---|
| `border` | draw a border around it (see [Layouts](layouts.md#borders)) |
| `title` | the border title, instead of the widget's name |
| `preferred_width`, `preferred_height` | see [Layouts](layouts.md#sizes) |
| `enabled` | `False` greys it out: it can't be focused and ignores clicks and keys |

The first positional argument is the main content: `Label("text")`, `Menu(items)`,
`Table(columns)`, `ProgressBar(0.5)`. Callbacks can be passed in (`on_click=fn`) or set
later (`button.on_click(fn)`).

Setting any attribute redraws the widget: `view.save.enabled = False`,
`view.bar.value = 0.5`. `widget.set(a=..., b=...)` changes several at once. After
changing a list in place, like `view.menu.items.append(...)`, call `widget.refresh()`.

## Text and Label

```python
Text("A long paragraph that wraps to fit.", align="center")
Label("Status: ready", style=style(fg="green"))
```

`text`, `align` (`"left"`, `"center"`, `"right"`), and `style` for the whole text (made
with [`style()`](themes.md#colors)). `Label` is a `Text` one line tall.

## Button

```python
Button("Save", on_click=save)
```

`text`, `on_click(fn)`. Click it, or press Enter or Space while it's focused.

## TextInput

```python
TextInput(placeholder="your name", on_submit=lambda value: print("hi", value))
```

`value`, `placeholder`, `on_submit(fn(value))` when Enter is pressed,
`on_change(fn(value))` after every edit. Click to move the cursor. See
[editing keys](#editing-keys) for the keys it understands.

- `password=True` shows `•` for each character.
- `keep_history=True` remembers each value submitted with Enter, and up/down bring
  earlier ones back, like a shell. Going down past the newest brings back what you were
  typing. The values are in `history` (oldest first), which you can fill or clear
  yourself. Password boxes never keep history.

```python
TextInput(placeholder="password", password=True)
TextInput(placeholder="command", keep_history=True, on_submit=run)
```

## TextArea

```python
TextArea(placeholder="notes", on_change=lambda value: save_draft(value))
```

A multi-line text box. Long lines wrap; Enter starts a new line. `value`,
`placeholder`, `on_change(fn(value))`.

Up/down move through the wrapped rows, Page Up/Down a screen at a time, and
Ctrl+Home/Ctrl+End go to the start or end of the text. The other
[editing keys](#editing-keys) work too, with Home/End and Ctrl+U/Ctrl+K acting on the
current line. Click to move the cursor, and scroll with the mouse wheel.

### Editing keys

Both text boxes understand:

| Key | |
|---|---|
| Left / Right | move one character |
| Ctrl+Left / Ctrl+Right (or Alt+Left / Alt+Right) | move one word |
| Home / End (or Ctrl+A / Ctrl+E) | start / end of the line |
| Backspace / Delete | delete one character |
| Ctrl+W (or Alt+Backspace) | delete the word before the cursor |
| Ctrl+U / Ctrl+K | delete to the start / end of the line |

Emoji and other wide characters take two columns, and the cursor accounts for them.
A [key binding](keys-and-focus.md#key-bindings) for one of these keys takes priority over
the text box.

## Checkbox and Toggle

```python
Checkbox("Remember me", checked=True, on_change=lambda checked: print(checked))
Toggle("Dark mode")
```

`text`, `checked`, `on_change(fn(checked))`, and `toggle()` to flip it from code.
`Toggle` is drawn as an on/off switch, and works the same.

## RadioGroup

```python
RadioGroup(["small", "medium", "large"], selected=1,
           on_change=lambda index, option: print(option))
```

`options`, `selected` (an index), `value` (the selected option), `horizontal=True` to
put the options side by side, `on_change(fn(index, option))`, and `select(index)`.
The arrow keys change the choice, or click one.

## Select

```python
Select(["small", "medium", "large"], on_change=lambda index, option: print(option))
Select(["red", "green", "blue"], selected=None, placeholder="pick a color")
```

Drawn like `[ medium      ▾]`. Click it, or press Enter or Space while it's focused, and
the list of options opens below it (or above, if there's no room). Pick one with the
mouse or the arrow keys and Enter; Escape or a click outside closes the list.

Up/down change the choice without opening the list, and Home/End jump to the first or
last option.

`options`, `selected` (an index, or `None` for nothing chosen yet), `value` (the chosen
option), `placeholder` (shown when nothing is chosen), `on_change(fn(index, option))`.
`select(index)`, `open()` and `close()` do those from code, and `is_open` says whether
the list is showing.

## Slider

```python
Slider(5, min=0, max=10, step=1, on_change=lambda value: print(value))
```

Drawn as `━━━━━●───── 5`. `value`, `min`, `max`, `step`, `show_value`,
`on_change(fn(value))`.

With a `step`, values snap to it; without one the slider is smooth and the arrow keys
move it a twentieth of the way. Drag it (the drag keeps going if the mouse leaves the
widget) or click on it. Left/right move one step, Page Up/Down five, Home/End jump to
the ends. `on_change` is only called when the user changes it, not when you set
`value` yourself.

## ProgressBar

```python
bar = ProgressBar(0.25)
bar.value = 0.5
```

`value` from 0 to 1, and `show_percent` to show or hide the percentage.

## Menu

```python
Menu(["apple", "banana", "cherry"], on_select=lambda index, item: print(item))
```

`items`, `selected` (an index), `on_select(fn(index, item))` on Enter or a click.
Up/down, Page Up/Down and Home/End move the selection; the mouse wheel scrolls. The
item under the mouse is highlighted with the `hover` [theme](themes.md) style, and
`hovered` is its index (or `None`).

## Tree

```python
Tree({"src": {"main.py": None, "util.py": None}, "docs": ["intro.md", "api.md"]},
     on_select=lambda path: print(path))
```

`nodes` is a dict of label → children. Children are another dict, a list, `None` for
an item with nothing inside, or a function that returns them, called the first time
the item is opened. That makes big trees cheap, like a file browser that only reads a
folder when you open it:

```python
import os

def folder(path):
    return lambda: {name: folder(os.path.join(path, name)) if os.path.isdir(os.path.join(path, name)) else None
                    for name in sorted(os.listdir(path))}

browser = Tree(folder("."), on_select=lambda path: print(os.path.join(*path)))
```

An item is picked out by its path, a tuple of labels like `("src", "main.py")`.
`selected` is the highlighted item's path, and `on_select(fn(path))` is called on
Enter or a click.

- Up/Down, Page Up/Down and Home/End move. Right opens an item, or moves into it if
  it's already open. Left closes it, or goes to its parent.
- `expand(path)`, `collapse(path)` and `toggle(path)` (the selected item by default),
  `expand_all()` and `collapse_all()`. `expand_all()` doesn't open function items that
  haven't been opened yet, so it won't read a whole disk.
- `reload()` forgets what the functions returned, so they're called again; use it after
  the data behind them changes. `reload(path)` does it for one item.

Two items with the same label under the same parent have the same path, so the tree
can't tell them apart. See `examples/files.py` for a file browser.

## Table

```python
Table(["name", "score"], rows=[["Ada", 98], ["Linus", 87]])
```

`columns` (header names) and `rows` (lists of values). Columns shrink to fit.
Scroll with the mouse wheel, or focus it (Tab or a click) and use up/down, Page Up/Down
and Home/End.

## Tabs

```python
from cmdgui import View, Panel, Tabs, TextInput, Button, Checkbox, Stdout, Label

class Profile(Panel):
    layout = """
        name   email
        save   .
    """
    name = TextInput(placeholder="your name")
    email = TextInput(placeholder="you@example.com")
    save = Button("Save")

class Settings(Tabs):
    profile = Profile()
    options = Panel(Checkbox("debug mode"), title="Options")
    log = Panel(Stdout())

class App(View):
    layout = "settings \n status"
    settings = Settings(on_change=lambda name: print("now on", name))
    status = Label("ready")

view = App()
view.settings.profile.name.value     # typed in your editor, through the class attributes
view.settings.show("log")
```

A `Panel` is a layout of widgets, written exactly like a `View` subclass: a `layout`
string and widgets as class attributes, or `Panel(layout, name=widget, ...)`. A panel
with one widget doesn't need a layout: `Panel(Stdout())`. Each panel is one tab.

A `Tabs` holds panels, as class attributes of a subclass (each `Tabs` gets its own
copies) or passed in: `Tabs(profile=Profile(), log=Panel(Stdout()))`. The tab bar
shows each panel's `title`, or its name.

- Switch by clicking a tab, with left/right (and Home/End) while the bar is focused,
  or with **Ctrl+Page Up / Ctrl+Page Down** from any widget inside the tabs.
- `show(name)`, `current` (the shown tab's name), `panel` (the shown `Panel`),
  `panels` (all of them by name), `on_change(fn(name))`.
- `view.settings.profile` is a panel, and `view.settings.profile.name` a widget in it.
- Hidden tabs keep everything: what you typed, scroll positions, and the widget you
  were focused on, which gets focus back when you return. Printed text still reaches a
  `Stdout` in a hidden tab.
- Widgets in a hidden tab aren't drawn, don't get clicks or keys, and Tab skips them.
- The `Tabs` widget asks for room for its largest tab, so switching tabs doesn't
  move the rest of the layout around.
- With a border (the default), the tabs sit above the content like a browser's: the
  shown tab is in a box that opens into the content below, and the content's border is
  shared with the widgets inside it. When the tab bar is focused, the box is highlighted.

  ```
  ┌─────────┐
  │ profile │ Options   log
  │         └────────────┬─ email ───────┐
  │your name             │you@example.com│
  ```

  `border=False` (or `{nb}` in the layout) gives a plain row of tab names instead, with
  no box or border.

Tabs can go inside panels (tabs within tabs) and inside popups. See
`examples/tabs.py`.

## Stdout

```python
log = Stdout()
print("goes to every Stdout")
log.print("only goes to this one", 42, sep=" | ")
log.print("shown in red", error=True)
```

Shows everything your program prints, with stderr in red. Scroll with the mouse wheel,
or focus it (Tab or a click) and use up/down, Page Up/Down and Home to go to the top.
While you're scrolled up, new output doesn't move what you're reading; End goes back to
the bottom and follows new output again.

- `print(*values, sep=" ", end="\n", error=False)`: like `print()`, but only shows up in
  this widget, and never on the real stdout.
- `write(text, error=False)`: add raw text to this widget only.
- `clear()`, and `max_lines` (default 500) for how much to keep.

Anything written to stderr, like a traceback, is printed again after the view closes,
so errors aren't lost.

## Graphics

```python
pic = Graphics(background="navy")
pic.circle(20, 10, 8, "gold", fill=True)
pic.line(0, 0, 40, 20, "red")
```

Draws in pixels, several to each character cell. `mode` picks how:

| `mode` | Pixels per cell | Colors | Good for |
|---|---|---|---|
| `"half"` (default) | 1×2, using `▀` | every pixel its own color | pictures, games; pixels are square |
| `"quad"` | 2×2, using `▖▗▘▝▚▞▙▟…` | two per cell; others snap to the nearer one | more detail, with some color fringing; pixels are twice as tall as wide |
| `"sextant"` | 2×3, using `🬀`–`🬻` | two per cell, like quad | three times half's pixels, nearly square |
| `"octant"` | 2×4 | two per cell, like quad | four times half's pixels, square |
| `"braille"` | 2×4 dots, using `⣿` | one per cell | charts and line drawings; filled shapes look dotted |

Half, quad and braille work in practically every terminal. Sextant uses characters
from Unicode 13 (2020) that newer terminals have (kitty, WezTerm, Ghostty, recent
iTerm2, Windows Terminal), and octant ones from Unicode 16 (2024) that very few fonts
have yet. If you see boxes or blanks, the terminal doesn't support that mode: run
`examples/graphics.py` to check yours.

The drawing code is the same for every mode, only the resolution changes:
`pixel_width` and `pixel_height` give the size in pixels.

Coordinates are in pixels from the top-left, and can be floats. Anything off the edge is
clipped. A color is anything [`style()`](themes.md#colors) takes (`"red"`, `208`,
`"#ff8800"`, `(255, 136, 0)`), or `None` for nothing, which shows `background` (or the
terminal's own background if that's `None` too).

| Method | |
|---|---|
| `pixel(x, y, color)`, `get(x, y)` | set or read one pixel |
| `clear(color=None)` | every pixel |
| `line(x0, y0, x1, y1, color)` | |
| `polyline(points, color, closed=False)` | lines joining the points |
| `rect(x, y, width, height, color, fill=False)` | |
| `circle(x, y, radius, color, fill=False)` | |
| `ellipse(x, y, rx, ry, color, fill=False)` | |
| `arc(x, y, radius, start, end, color)` | angles in degrees, 0 is right, clockwise |
| `bezier(points, color)` | 3 points for a quadratic curve, 4 for cubic, or more |
| `polygon(points, color, fill=False)` | filled with the even-odd rule, so a self-crossing star has a hole |
| `image(rows, x=0, y=0)` | copy in rows of colors; `None` is see-through |
| `text(x, y, text, color, scale=1, fix_aspect=True)` | write in a 3×5 pixel font, its top-left at (x, y) |
| `text_size(text, scale=1, fix_aspect=True)` | how many pixels (wide, tall) `text()` would take |

### Text

`text()` draws in a small pixel font, so it works in every mode and lines up with what
you draw. It has capitals only (lowercase is drawn as capitals), and draws characters it
doesn't know as `?`. `scale=2` draws each font pixel as 2×2.

In quad and sextant modes pixels are taller than they're wide, which would make letters
tall and thin, so `text()` widens them to keep their shape. Pass `fix_aspect=False` to
draw the font pixel for pixel instead (to both `text()` and `text_size()`, so they
agree). Centre text with `text_size()`:

```python
width, height = g.text_size("GAME OVER", 2)
g.text((g.pixel_width - width) / 2, (g.pixel_height - height) / 2, "GAME OVER", "red", 2)
```

Each character is 4 pixels wide (with the gap) and each line 6 tall, so in half mode a
line of text takes 3 rows of the terminal. For small readable text, a `Label` next to
the picture is often better.

### Keeping the picture, or painting it each time

Whatever you draw stays until you draw over it. When the widget is resized, the part
that still fits is kept. Drawing works once the view has laid the widget out, so draw
after creating the view.

Or give it `on_paint=fn(graphics)`, which draws the whole picture. It's called on a
cleared widget whenever the size or mode changes, and when you call `repaint()`. That's
the way to handle resizing, and to animate:

```python
def paint(g):
    t = time.monotonic()
    g.circle(g.pixel_width / 2 + 10 * math.cos(t), g.pixel_height / 2, 5, "red", fill=True)

view.every(1 / 30, view.pic.repaint)   # 30 frames a second
```

`on_paint` and timers run between frames, so the screen never shows half a picture. To
draw several things from another thread without that, wrap them in `with pic.batch():`.

### Mouse

`on_click(fn(x, y))` gets the pixel clicked, and `on_drag(fn(x, y))` is called as the
mouse moves with the button held. A cell holds several pixels, so these give the
top-left pixel of the cell; `mouse_pixel()` does the same at any time.

### Round shapes in quad and sextant modes

Quad pixels are twice as tall as they're wide, so `circle()` comes out tall and thin
(sextant pixels a little). `pixel_aspect` is 2 in quad mode, 1.33 in sextant and 1 in
the others; for a round circle in every mode, use
`ellipse(x, y, r, r / g.pixel_aspect, color)`.

See `examples/graphics.py` for an animation and a sketch pad.
