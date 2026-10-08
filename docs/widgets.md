# Widgets

| Type | Class | What it does |
|---|---|---|
| `text` | [`Text`](#text-and-label) | Wrapped text, or [Markdown](#markdown) |
| `label` | [`Label`](#text-and-label) | One line of text |
| `button` | [`Button`](#button) | Click, or Enter/Space when focused |
| `text_input` | [`TextInput`](#textinput) | A one-line text box |
| `text_area` | [`TextArea`](#textarea) | A multi-line text box |
| `checkbox` | [`Checkbox`](#checkbox-and-toggle) | A box to tick |
| `toggle` | [`Toggle`](#checkbox-and-toggle) | An on/off switch |
| `radio_group` | [`RadioGroup`](#radiogroup) | Pick one of several options |
| `select` | [`Select`](#select) | A dropdown: pick one option from a list that opens |
| `calendar` | [`Calendar`](#calendar-and-datepicker) | A month to pick a day from |
| `date_picker` | [`DatePicker`](#calendar-and-datepicker) | A date that opens a calendar to change it |
| `slider` | [`Slider`](#slider) | Pick a number by dragging |
| `progress_bar` | [`ProgressBar`](#progressbar) | A bar from 0 to 1 |
| `menu` | [`Menu`](#menu) | A list to pick from |
| `tree` | [`Tree`](#tree) | Nested items that fold open |
| `table` | [`Table`](#table) | Rows and columns |
| `tabs` | [`Tabs`](#tabs) | Several panels or widgets in one place, with a bar to switch between them |
| `stdout` | [`Stdout`](#stdout) | Everything your program prints |
| `log` | [`Log`](#log) | Log messages with levels in colour, filtering and search |
| `terminal` | [`Terminal`](#terminal) | A program running in a terminal of its own: a shell, a REPL, top, vim |
| `key_hints` | [`KeyHints`](keys-and-focus.md#a-footer-of-the-keys-that-work) | A footer of the keys that work right now |
| `graphics` | [`Graphics`](#graphics) | Draw in pixels: lines, shapes, curves |

## Common to every widget

Every widget takes these, as constructor arguments or attributes:

| | |
|---|---|
| `border` | draw a border around it (see [Layouts](layouts.md#borders)) |
| `border_style` | `"single"`, `"rounded"`, `"heavy"`, `"double"` or `"ascii"`; `None` for the view's (see [border styles](layouts.md#border-styles)) |
| `title` | the border title, instead of the widget's name |
| `preferred_width`, `preferred_height` | see [Layouts](layouts.md#sizes) |
| `enabled` | `False` greys it out: it can't be focused and ignores clicks and keys |
| `visible` | `False` hides it, and the layout closes up around it (see [hiding widgets](layouts.md#hiding-widgets)) |
| `tab_stop` | `False`: Tab skips it, though a click still focuses it |
| `default_menu` | `False` leaves out its built-in [right-click](#right-click-menus) items |

Most of these can also be set from the layout string with [flags](layouts.md#flags):
`log{-b,h=6}`.

The first positional argument is the main content: `Label("text")`, `Menu(items)`,
`Table(columns)`, `ProgressBar(0.5)`. Callbacks can be passed in (`on_click=fn`) or set
later (`button.on_click(fn)`).

Setting any attribute redraws the widget: `view.save.enabled = False`,
`view.bar.value = 0.5`. `widget.set(a=..., b=...)` changes several at once. After
changing a list in place, like `view.menu.items.append(...)`, call `widget.refresh()`.

## Right-click menus

Any widget can have a menu that a right-click opens, or **Shift+F10** (or the Menu key)
while it's focused:

```python
files.menu_item("Delete", lambda ctx: delete(ctx["item"]))
files.menu_item("Rename…", lambda ctx: rename(ctx["item"]),
                show=lambda ctx: 1 if ctx["item"] is not None else -1)
files.menu_item("Rename…", None)    # remove it
```

- `on_click(ctx)` runs the item. `ctx` is a dict saying what was clicked: always
  `widget`, and `x` and `y` relative to it, plus more for some widgets (below).
- `show(ctx)` decides how the item looks this time: `1` to click, `0` greyed out, `-1`
  left out. Without `show` it's always there to click.
- Items on a [panel](layouts.md#panels-in-a-layout) show in the menus of every widget
  inside it, after the widget's own, with a line between.
- Some widgets have built-in items, shown after yours; `default_menu=False` turns them off.
- Pick with a click, or up/down and Enter. Escape or a click elsewhere closes it.
- For your own widgets, override `menu_context(x, y)` to add keys, starting from
  `super().menu_context(x, y)`.

| Widget | Extra `ctx` keys | Built-in items |
|---|---|---|
| `Menu` | `index`, `item` (`None` off the items) | |
| `Tree` | `path`, `node` (the label) | |
| `Table` | `index` (into `rows`), `row`, `column` | Copy row |
| `TextInput`, `TextArea` | | Cut, Copy, Paste, Select all |
| `Log` | `line`, `level` | Copy line, Clear |
| `Stdout` | `line` | Copy line, Clear |

With Shift+F10, `ctx` is for the selected item. Paste in the menu pastes what was last
copied in your program; pasting from elsewhere is done by the terminal (Cmd+V or
Ctrl+Shift+V). See `examples/dialogs.py` and `examples/widgets.py`.

## Text and Label

```python
Text("A long paragraph that wraps to fit.", align="center")
Label("Status: ready", style=style(fg="green"))
```

`text`, `align` (`"left"`, `"center"`, `"right"`), and `style` for the whole text (made
with [`style()`](themes.md#colors)). `Label` is a `Text` one line tall.

### Styled text

Style parts of the text with markup:

```python
Label("[bold red]Error:[/] couldn't open [cyan]notes.txt[/]")
Text("[on blue] NEW [/] [italic]fresh from the oven[/]")
```

| Markup | |
|---|---|
| `[bold]` `[dim]` `[italic]` `[underline]` `[reverse]` | text styles |
| `[red]` `[hot_pink]` `[#ff8800]` | a color: any [color name](themes.md#colors) or hex |
| `[on blue]` | a background color |
| `[bold yellow on red]` | several at once |
| `[/]` | ends the last one; `[/bold]` ends the last `[bold]`; anything still open ends with the text |
| `\[` | a literal `[` |

Brackets that aren't a style are left as they are, so `[1, 2]` and `[x]` show as
written. Use names or hex for colors, not palette numbers, so `[1]` stays text too.

Markup works in `Text`, `Label`, `Button`, `Checkbox` and `Toggle`. `markup=False` turns
it off. `Menu`, `Tree`, `Table` and `Log` usually show data, where brackets are common, so
there it's off unless you pass `markup=True`. To put a value into markup safely, escape
it: `Label(f"opened [cyan]{escape(name)}[/]")`, with `escape` from `cmdgui.shorts`.

### Markdown

```python
readme = Text(open("README.md").read(), markdown=True, on_link=open_page)
```

With `markdown=True` the text is Markdown: headings, **bold**, *italic*, `code`,
~~strikethrough~~, links, bullet, numbered and `[ ]` task lists (nested), `>` quotes,
code blocks, `---` lines and tables. (`[style]` markup isn't read then, since Markdown
uses square brackets for links.)

- Longer than the box, it scrolls: the mouse wheel, or click it (or Tab to it) and use
  up/down, Page Up/Down, Space, Home and End. `scroll` is how far down it is.
- Clicking a link calls `on_link(url)`, or without one opens it in your browser. A link
  to a heading on the same page (`#install`) scrolls to it, and so does
  `text.scroll_to("install")`: a heading's anchor is made the way GitHub makes them.
- The colours are the `md_...` [theme](themes.md) keys.

See `examples/markdown.py`, a reader for this project's docs.

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
`on_change(fn(value))` after every edit. Click to move the cursor, or drag to select.
See [editing keys](#editing-keys) for the keys it understands.

- `prefix` and `suffix` show dim text before and after the value, which isn't part of
  it: `TextInput(prefix="https://")`, `TextInput(suffix=" kg")`. They show once there's
  text or the box is focused (the `placeholder` shows before that).
- `suggest` offers a completion, shown dim after what's typed, like a shell's
  autosuggestions. **Tab**, **Right** or **End** fills it in. Give it a list (the first
  item starting with what's typed, ignoring case, is suggested) or a function that's
  given the text and returns the whole suggested value, or `None`:

  ```python
  TextInput(suggest=["github.com", "gitlab.com", "google.com"])
  TextInput(suggest=lambda text: next((c for c in commands if c.startswith(text)), None))
  ```

  `suggestion` is the current one, and `accept_suggestion()` fills it in from code.

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
`placeholder`, `on_change(fn(value))`. Pasted text keeps its lines.

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
| Shift with any of the moves above (Shift+Left, Ctrl+Shift+Right, Shift+End...) | select |
| Ctrl+C / Ctrl+X / Ctrl+V | copy / cut / paste |

Drag with the mouse to select, too. Typing or pasting replaces the selection, and
Backspace or Delete removes it.

**Copy** puts the text on the system clipboard as far as the terminal allows: it sends
the OSC 52 code, which most modern terminals act on (kitty, WezTerm, Ghostty, Alacritty,
Windows Terminal; iTerm2 once it's allowed in its settings; not macOS's Terminal.app),
and runs `pbcopy`, `wl-copy`, `xclip` or `xsel` when running locally. `cmdgui.clipboard`
has `copy(text)` for your own code. A password box can't be copied from.

**Cmd+C on macOS** can't copy from a text box: the terminal keeps Cmd shortcuts for
itself and never sends them to the app. Use Ctrl+C, or `View(copy_on_select=True)`,
which copies whatever you select with the mouse as soon as you let go. To select with
the terminal itself instead (from anywhere on screen, then Cmd+C), hold a key while
dragging: Option in iTerm2, Fn in Terminal.app, Shift in kitty, WezTerm, Ghostty and
Alacritty.

**Paste** with your terminal's own paste (Cmd+V, or Ctrl+Shift+V) to paste from the
system clipboard: the text arrives in one go, so a pasted newline isn't Enter. A
one-line box turns newlines into spaces. Ctrl+V pastes what was last copied in the app.

Emoji and other wide characters take two columns, and the cursor accounts for them.
A [key binding](keys-and-focus.md#key-bindings) for one of these keys takes priority over
the text box.

## Checkbox and Toggle

```python
Checkbox("Remember me", checked=True, on_change=lambda checked: print(checked))
Toggle("Dark mode")
```

`text`, `checked` (or `value`, the same thing), `on_change(fn(checked))`, and `toggle()`
to flip it from code.
`Toggle` is drawn as an on/off switch, and works the same.

## RadioGroup

```python
RadioGroup(["small", "medium", "large"], selected=1,
           on_change=lambda index, option: print(option))
```

`options`, `selected` (an index), `value` (the selected option; set it to an option to
select that one), `horizontal=True` to
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
option; set it to an option, or `None`), `placeholder` (shown when nothing is chosen), `on_change(fn(index, option))`.
`select(index)`, `open()` and `close()` do those from code, and `is_open` says whether
the list is showing.

## Calendar and DatePicker

```python
from datetime import date

Calendar(date(2026, 10, 6), on_select=lambda day: print("picked", day))
DatePicker(placeholder="due date", format="%d %b %Y", min_date=date.today(),
           on_change=lambda day: print("due", day))
```

A `Calendar` shows a month to pick a day from. Click a day, or focus it and move with the
arrow keys (a day left and right, a week up and down), Page Up/Down for the month before
or after, and Home/End for the start or end of the month. Enter (or a click) calls
`on_select`. To see another month without changing the day, click the `‹` `›` either side
of its name, or scroll.

A `DatePicker` is one line, like a [`Select`](#select): it shows the date, and opens a
calendar below it when clicked (or with Enter or Space while focused). Up/down change it
by a day without opening it.

- `value`: the chosen `date`, or `None` (a `datetime` or an ISO string like
  `"2026-01-05"` works too, and is turned into a date). Set it, or call `choose(day)` to
  also call `on_change`.
- `min_date`, `max_date`: days outside these are greyed out and can't be chosen.
- `first_weekday`: `0` for weeks starting on Monday (the default), `6` for Sunday.
- `on_change(fn(date))`: the chosen day changed (by the arrow keys too, in a calendar).
- `Calendar`: `on_select(fn(date))` on Enter or a click, `month` (the shown
  `(year, month)`), `show_month(year, month)`. Today is underlined.
- `DatePicker`: `format` (for `strftime`, `"%Y-%m-%d"` by default), `placeholder`,
  `open()`, `close()`.

See `examples/dates.py`.

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

for path in bar.track(files):    # the bar keeps up: 12/40 · 8s left
    copy(path)
```

`value` from 0 to 1, `show_percent` to show or hide the percentage, and `label` for text
of your own in its place.

`track(items, total=None)` goes through items for you, moving the bar along with how many
are done and about how long is left, and when it's finished how long it took. It's an
ordinary loop in your program, so there's nothing else to wire up.

- `total` is how many there are, for a generator that can't say. Without one, a block
  slides along the bar and the label just counts.
- Updates are limited to about 20 a second, so a fast loop isn't slowed down.
- `break` out early and the bar stays where it got to.

See `examples/progress.py`.

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

**Picking a row.** Focus it (Tab or a click) and move with up/down, Page Up/Down and
Home/End; the mouse wheel scrolls without moving the highlight. Enter or a click calls
`on_select(fn(index, row))`, and `on_change(fn(index, row))` is called whenever the
highlighted row changes. `selected` is the highlighted row's index (or `None`), `value`
the row itself, and `select(index)` highlights one from code.

**Sorting.** Click a column's header to sort by it, and again to reverse; ▲ or ▼ marks
it. While the table is focused, the number keys 1 to 9 do the same for the first nine
columns. From code: `sort("score")`, `sort("score", reverse=True)` or `sort(None)` for the
order of `rows`; `sort_column` and `sort_reverse` say how it's sorted, and
`on_sort(fn(column, reverse))` is called when the user sorts. `sortable=False` turns
the header clicks and keys off.

- Numbers sort by value, and so do cells starting with one, so `9%` comes before `42%`
  and `1,200` after `900`. Text sorts ignoring case, after numbers.
- `sort_keys` gives a column its own sort key, by name or index:
  `Table(..., sort_keys={"uptime": parse_duration})`.
- Sorting doesn't change `rows`, and indexes (`selected`, the callbacks, `select()`)
  are always into `rows` as you gave them. So you can replace `rows` as often as you
  like, as a live table does, and the sorting and highlight stay.

```python
table = Table(["name", "score"], rows=[["Ada", 98], ["Linus", 87], ["Grace", 91]],
              on_select=lambda index, row: print("picked", row[0]))
table.sort("score", reverse=True)   # highest first
```

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
    log = Stdout()

class App(View):
    layout = "settings \n status"
    settings = Settings(on_change=lambda name: print("now on", name))
    status = Label("ready")

view = App()
view.settings.profile.name.value     # typed in your editor, through the class attributes
view.settings.show("log")
```

Each tab is a widget. Usually that's a [`Panel`](layouts.md#panels-in-a-layout), a
layout of widgets written exactly like a `View` subclass, but a tab that's just one
widget doesn't need one: `log = Stdout()`, and then `view.settings.log` is the widget.

A `Tabs` holds its tabs as class attributes of a subclass (each `Tabs` gets its own
copies) or passed in: `Tabs(profile=Profile(), log=Stdout())`. The tab bar shows each
tab's `title`, or its name. `Tabs` is itself a kind of panel, so `view.settings["log"]`
and `view.settings.get("log", Stdout)` work too.

- Switch by clicking a tab, with left/right (and Home/End) while the bar is focused,
  or with **Ctrl+Page Up / Ctrl+Page Down** from any widget inside the tabs.
- `show(name)`, `current` (the shown tab's name), `shown` (the shown tab's panel or
  widget), `named` (all of them by name), `on_change(fn(name))`.
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

  `border=False` (or `{-b}` in the layout) gives a plain row of tab names instead, with
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

## Terminal

```python
shell = Terminal()                           # your shell ($SHELL)
repl = Terminal([sys.executable, "-q"])      # a list runs the program directly
build = Terminal("make 2>&1 | less")         # a string runs through your shell
```

Runs a program in a terminal of its own, inside the layout. Anything that works in a
terminal works here, full-screen programs like `top`, `less` and `vim` included: colours,
cursor movement, the alternative screen and wide characters are all handled. It starts
when it's first laid out, at the right size, and the program is told when it's resized
(by the window, or by dragging a [line](layouts.md#draggable-lines)).

- Click it or Tab to it to type. While it's focused **every key goes to the program**,
  Tab, Escape and Ctrl+C included, so press **Ctrl+]** (`release_key`) to move on, or
  click another widget. A [`KeyHints`](keys-and-focus.md#a-footer-of-the-keys-that-work)
  footer shows this.
- Pasting works, and so does the mouse wheel: it scrolls back through what's scrolled off
  the top (`scrollback`, 1000 lines), or in a full-screen program sends up/down keys.
- `run("ls -la")` types a command and Enter; `write(text)` sends anything, as if typed.
- `on_exit(fn(code))` is called when the program ends, which shows `[exited with code N]`.
  `running`, `exit_code`, `restart()`, `kill()`, and `start()` to run it again.
- `cwd`, and `env` for variables to add. `TERM` is `xterm-256color`.
- `program_title`: the window title the program set, if any.
- macOS and Linux only. Programs that use the mouse themselves don't get mouse clicks.

See `examples/terminal.py`.

## Log

```python
log = Log(level="info")
log.info("server started on port", 8080)
log.warning("disk 91% full")
log.add("custom", level="error", time=some_datetime)

logging.getLogger().addHandler(log.handler())   # Python's logging goes here too
```

Log messages, newest at the bottom, each with its time and level:

```
16:19:24 INFO  request from user 430 served
16:19:25 WARN  job 251 is slow, took 2.4s
16:19:25 ERROR couldn't reach the database for job 596
```

The levels are `"debug"`, `"info"`, `"warning"`, `"error"` and `"critical"`, the same as
Python's `logging` (whose level numbers work too). Each level has its colour from the
theme (`log_debug` and so on); error and critical messages are red.

- `debug()`, `info()`, `warning()`, `error()`, `critical()`: add a message, joining the
  values like `print()` does. `add(*values, level="info", time=None)` takes the level, and
  a `datetime` or timestamp for the time.
- `level`: hide messages less important than this, e.g. `log.level = "warning"`.
- `search`: show only the messages containing this text (ignoring case), with the
  matches highlighted. Pair it with a `TextInput`:
  `TextInput(on_change=lambda text: log.set(search=text))`.
- `handler(level=...)`: a `logging.Handler` that sends records here. It shows just the
  message (and the traceback, for `logger.exception()`); give it a formatter for more,
  like `handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))`.
- `show_time`, `time_format` (`"%H:%M:%S"`), `max_entries` (1000, the oldest go first).
- `clear()`, `count(level=None)`, `entries` (every message kept, as
  `(datetime, level, message)`).

Scrolling works like [`Stdout`](#stdout): the mouse wheel, or the arrow keys, Page
Up/Down and Home while focused. While scrolled up, new messages don't move what you're
reading; End goes back to the bottom. Long messages wrap, lined up after the level.

Adding messages is safe from any thread. See `examples/log_viewer.py`.

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
| `line(x0, y0, x1, y1, color, thickness=1)` | |
| `polyline(points, color, closed=False, thickness=1)` | lines joining the points |
| `rect(x, y, width, height, color, fill=False, thickness=1)` | a thick outline goes inwards |
| `circle(x, y, radius, color, fill=False, thickness=1)` | |
| `ellipse(x, y, rx, ry, color, fill=False, thickness=1)` | |
| `arc(x, y, radius, start, end, color, thickness=1)` | angles in degrees, 0 is right, clockwise |
| `bezier(points, color, thickness=1)` | 3 points for a quadratic curve, 4 for cubic, or more |
| `polygon(points, color, fill=False, thickness=1)` | filled with the even-odd rule, so a self-crossing star has a hole |
| `image(rows, x=0, y=0)` | copy in rows of colors; `None` is see-through |
| `text(x, y, text, color, scale=1, fix_aspect=None)` | write in a 3×5 pixel font, its top-left at (x, y) |
| `text_size(text, scale=1, fix_aspect=None)` | how many pixels (wide, tall) `text()` would take |

`thickness` is in pixels: `line(0, 0, 40, 20, "red", thickness=3)` is 3 pixels wide, with
round ends. Thick lines and outlines are centred on the line, except a rectangle's, which
stays inside it.

### Text

`text()` draws in a small pixel font, so it works in every mode and lines up with what
you draw. It has capitals only (lowercase is drawn as capitals), and draws characters it
doesn't know as `?`. `scale=2` draws each font pixel as 2×2.

In quad and sextant modes pixels are taller than they're wide, which would make letters
tall and thin, so `text()` widens them to keep their shape (see
[round shapes](#round-shapes-in-quad-and-sextant-modes)). Pass `fix_aspect=False` to
draw the font pixel for pixel instead (to both `text()` and `text_size()`, so they
agree); `None` follows the widget's setting. Centre text with `text_size()`:

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

Quad pixels are twice as tall as they're wide (sextant ones a third taller), so drawn
pixel for pixel, a circle would come out tall and thin. With `fix_aspect=True` (the
default), round things are corrected to look right in every mode:

- `circle()` and `arc()` are round, `radius` pixels across from the centre.
- `ellipse()`'s `ry` is measured like `rx`, so `ellipse(x, y, 20, 10, ...)` is twice as
  wide as tall on screen.
- Thick lines are as thick going across as going down.
- `text()` widens letters to keep their shape.

Positions aren't changed: `(x, y)` is always a pixel, and lines, rectangles, polygons and
curves go through exactly the points you give. `pixel_aspect` is how many times taller
than wide a pixel is (2 in quad mode, 1.33 in sextant, 1 in the others), for working out
positions yourself: a point `r` below the centre of a circle is at `cy + r / g.pixel_aspect`.

`Graphics(fix_aspect=False)` turns it off, so every size is in pixels as drawn.

See `examples/graphics.py` for an animation and a sketch pad.
