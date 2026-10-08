# cmdgui docs

Simple terminal GUIs in Python. Draw your layout as text, fill in the widgets,
and keep writing your program. The view runs on its own thread, so there's no
event loop to hand control to and no draw calls to make.

- [Layouts](layouts.md): the layout string, sizes and borders
- [Widgets](widgets.md): every built-in widget
- [Popups](popups.md): dialogs, dropdowns and menus that float over the layout
- [Keys and focus](keys-and-focus.md): Tab, key bindings, the quit key
- [Themes and colors](themes.md): restyling widgets, and every color you can use
- [Your own widgets](custom-widgets.md): subclassing `Widget`

## Three ways to build a view

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

## Changing widgets

Setting an attribute redraws the widget, from any thread: `view.bar.value = 0.5`
just works, and `widget.set(text=..., align=...)` changes several at once. If you
change a list in place (`view.menu.items.append(...)`), call `widget.refresh()`.

Callbacks like `on_click` run on the view's thread. Keep them quick: while one is
running, the view can't redraw or handle input. Start a `threading.Thread` for
slow work, and set widget attributes from it as it goes.

## Form values

Every input has a `value`, and a view or panel gathers them all into a dict:

```python
view.values           # {"name": "Ada", "debug": True, "options": {"size": 12}}
view.values = saved   # fill them in again
view.on_values_change(lambda values: save(values))
```

- The inputs are `TextInput`, `TextArea`, `Checkbox`, `Toggle`, `RadioGroup`, `Select`,
  `Slider`, `Calendar` and `DatePicker`, by their names. Labels, buttons, lists and tables
  aren't in it.
- A [panel](layouts.md#panels-in-a-layout) or `Tabs` inside gives a dict of its own, so
  the shape follows the code: `view.values["settings"]["profile"]["name"]` is
  `view.settings.profile.name.value`. Every panel has `values` too.
- Setting `values` changes only the names you give, and like setting a widget's `value`
  it doesn't call their `on_change`. A name that isn't there is an error, so typos
  don't go unnoticed.
- `on_values_change(fn(values))` is called whenever an input inside changes, at the same
  times as the input's own `on_change`: for saving as you go, or showing that there are
  unsaved changes (`view.values != saved`).
- The values are plain Python: strings, numbers, booleans, the chosen option, and dates.
  `json.dumps(values, default=str)` saves dates as `"2026-01-05"`, and setting that string
  back gives a date again.

See `examples/form.py`.

## Timers

```python
view.every(1, update_clock)                      # every second
view.after(5, lambda: view.status.set(text=""))  # once, in 5 seconds

timer = view.every(0.5, blink)
timer.cancel()                                   # stop it
```

Both return a `Timer` with `cancel()` and `active`. Like other callbacks, timers run on
the view's thread, so they can change widgets freely but should be quick. A timer that
runs late doesn't try to catch up: the next call waits a full interval. Timers stop when
the view closes.

## Running and quitting

```python
with View("...") as view:
    ...
    view.wait()   # blocks until q, view.quit() or Ctrl+C
```

Without `wait()`, the quit key ends your program as if it had finished. Your
program can also keep looping while the view is open, checking `view.running`:

```python
view = App()
while view.running:
    view.bar.value = get_progress()
    time.sleep(0.1)
```

If anything raises, in your code or inside a callback, the terminal is put back
to normal first, so the traceback is visible.

## Inline views

A view normally takes over the whole terminal. `inline` draws it in a few rows under the
prompt instead, like a progress display:

```python
view = Downloads(inline=True)   # as many rows as the layout needs; or inline=8 for 8 rows
print("finished photos.zip")    # shows above the view, like normal output
view.stop()                     # the last frame stays, and the prompt comes back below it
```

- What your program prints goes above the view and scrolls up as usual (or into a
  `Stdout` widget, if the view has one).
- When it closes, the last frame stays in your scrollback; `keep_on_exit=False` clears it.
- Everything else works as in a full-screen view: widgets, the mouse, popups (which stay
  inside the view's rows), timers.

See `examples/inline.py`.

| Method | |
|---|---|
| `view.wait()` | block until the view closes |
| `view.quit()` | close the view and end the program |
| `view.stop()` | close the view and put the terminal back, without ending the program |
| `view.refresh()` | redraw everything |
| `view.relayout()` | work out the layout again, e.g. after changing a widget's preferred size |
| `view.add(widget)` | add a widget outside the layout; set its `x`, `y`, `width`, `height` yourself |
