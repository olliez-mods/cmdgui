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
- A popup with one widget doesn't need a layout: `Popup(Menu(items))`, or a subclass
  with a single widget.
- `popup.copy()` makes a separate copy, to show the same kind of popup twice.

## Settings

As class attributes or constructor arguments:

| Setting | Default | |
|---|---|---|
| `modal` | `True` | blocks clicks and focus for everything underneath |
| `close_on_escape` | `True` | |
| `close_on_outside_click` | `False` | for a modal popup the click just closes it; otherwise it goes through too |
| `keep_typing` | `False` | the focused text box keeps getting typed text, while arrows and Enter go to the popup (autocomplete, command menus) |
| `border`, `title` | `True`, `None` | |
| `width`, `height` | `None` | outer size; `None` fits the content |

Inside a popup, a widget's border title is only shown if you set its `title`.

## Examples

- `examples/popups.py`: a dialog and a dropdown
- `examples/simple_console.py`: a `/` command menu that opens while you type, using `keep_typing`
