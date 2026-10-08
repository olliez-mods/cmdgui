# Keys and focus

- **Tab** / **Shift+Tab** or a click moves focus between widgets that take input.
  Disabled and hidden widgets are skipped, and so are widgets with `tab_stop=False`
  (`-f` in the layout), though a click still focuses those.
- Key presses go to the focused widget; typed characters go to a focused text box first.
- `view.focus(widget)` focuses a widget from code, `view.focus(None)` removes focus,
  and `view.focused` is the focused widget (or `None`).

## Key bindings

```python
view.on_key("ctrl+s", save)
view.on_key("ctrl+s", save, "Save")   # with a label, a KeyHints footer shows it
view.on_key("ctrl+s", None)   # remove it
```

A binding runs when its key is pressed, unless a focused text box takes it as typing, or
a dialog from `view.confirm()`, `prompt()` or `choose()` is waiting for an answer (the quit
key still works then).
Key names:

- letters and symbols as typed: `a`, `A`, `+`
- `enter`, `escape`, `tab`, `shift_tab`, `space`, `backspace`, `delete`, `insert`
- `up`, `down`, `left`, `right`, `home`, `end`, `page_up`, `page_down`
- with modifiers: `ctrl+a`, `alt+x`, `ctrl+up`, `shift+left`, `ctrl+shift+right`

## A footer of the keys that work

Put a `KeyHints` widget in the layout, usually as the bottom row, and it shows the keys
that work right now:

```
 ↑↓ Move   Enter Select   d Delete   r Rename   o Open with   q Quit
```

```python
class App(View):
    layout = """
        files  editor
        hints  -
    """
    hints = KeyHints()
    ...

view.on_key("d", delete, "Delete")
```

It keeps up by itself, showing in order:

- `Esc` when a popup is open (Cancel for a dialog, Close otherwise)
- the focused widget's keys, like a list's `↑↓ Move` and `Enter Select`, and keys from
  what it's inside, like `Ctrl+PgUp/PgDn Switch tab` in a `Tabs`
- your key bindings that have a label, leaving out the ones that wouldn't run right now:
  single keys while you type in a text box, and all of them while a dialog waits
- the quit key (`Ctrl+C` while typing, since `q` would type a q)

When there isn't room for them all, the rest are cut off with `…`. The colours are the
`hint_key` and `hint` [theme](themes.md) keys, and `separator` (three spaces) goes between
them. `view.key_hints()` gives the same list as `(key, label)` pairs, for a footer of your
own, and your own widgets can add theirs (see [Your own widgets](custom-widgets.md)).

## The quit key

`View(layout, quit_key="q")` sets the quit key; `quit_key=None` turns it off. Typing `q`
into a focused text box types it rather than quitting.

Ctrl+C quits too (raising `KeyboardInterrupt`, as usual), except in a focused text box
with text selected, where it copies. Ctrl+Z, Ctrl+S, Ctrl+Q and Ctrl+V reach the app as
keys you can bind, rather than being taken by the terminal.
