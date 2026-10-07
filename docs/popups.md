# Popups

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
  `at=(x, y)`. It flips to the other side if there's no room. Showing a popup that's
  already open just moves it.
- `popup.close()`, `popup.is_open`, `popup.on_close(fn)`.
- `view.alert("Saved!", title="Done")` shows a message with an OK button.
- Without a layout, a popup's widgets go one above the other in the order they're
  declared, so a popup with one widget is just `Popup(Menu(items))`.
- `popup.copy()` makes a separate copy, to show the same kind of popup twice.
- A popup is a [`Panel`](layouts.md#panels-in-a-layout) that floats, so it can hold
  anything a panel can, including `Tabs`. While it's open, `popup.x`, `popup.y`,
  `popup.width` and `popup.height` are where it is on screen, border included.

## Asking a question

These show a dialog and wait for the answer, so you get it back like a function's result:

```python
if view.confirm("Delete notes.txt?", yes="Delete"):    # True, or False for Cancel/Escape
    os.remove("notes.txt")

name = view.prompt("Rename to:", value="notes.txt")    # the text, or None if cancelled
app = view.choose(["vim", "nano", "less"], "Open with:")  # the item picked, or None
```

| | Returns | Options |
|---|---|---|
| `confirm(message)` | `True` / `False` | `title`, `yes="OK"`, `no="Cancel"` |
| `prompt(message)` | the text / `None` | `value` (to start with), `title`, `placeholder`, `password` |
| `choose(items)` | the item / `None` | `message`, `title`, `selected` (the index to start on) |

They work from anywhere:

- From your own code, they wait while the view keeps running.
- From a callback (a button's `on_click`, a key binding, a timer), they wait too: the view
  keeps handling input and drawing until the dialog is answered, then your callback
  carries on. There's no need to split your code into "ask" and "on answer" parts.

While one is open, your key bindings wait (except the quit key), so a key can't open a
second dialog on top of the first. `examples/dialogs.py` uses all three.

## Notifications

`view.notify()` shows a short message in the bottom right corner for a few seconds:

```python
view.notify("Saved [bold]notes.txt[/]", "ok")
view.notify("Couldn't reach the server", "error", seconds=None)  # stays until clicked
```

- Levels: `"info"` (the default), `"ok"`, `"warning"` and `"error"`, each with its own icon
  and colour (the `toast_...` [theme](themes.md) keys).
- `seconds` is how long it stays (3 by default); `None` keeps it until it's clicked.
  Clicking one closes it early.
- It floats over everything but doesn't take focus or block anything. Newer ones go at
  the bottom and push older ones up; at most 5 show at once.
- It returns a `Toast`: `toast.close()`, `toast.is_open`. Safe to call from any thread.

## Settings

As class attributes or constructor arguments:

| Setting | Default | |
|---|---|---|
| `modal` | `True` | blocks clicks and focus for everything underneath |
| `close_on_escape` | `True` | |
| `close_on_outside_click` | `False` | for a modal popup the click just closes it; otherwise it goes through too |
| `keep_typing` | `False` | the focused text box keeps getting typed text, while arrows and Enter go to the popup (autocomplete, command menus) |
| `border`, `title` | `True`, `None` | |
| `preferred_width`, `preferred_height` | `None` | the size inside the border, as for a widget (`40`, `"30+"`, `"20-40"`); `None` fits the content |

Inside a popup, a widget's border title is only shown if you set its `title`.

## Examples

- `examples/popups.py`: a dialog, a dropdown, and a Notify button that cycles through the
  notification levels
- `examples/dialogs.py`: `confirm`, `prompt` and `choose`, from your code and from
  callbacks, with notifications for what they did
- `examples/simple_console.py`: a `/` command menu that opens while you type, using `keep_typing`
