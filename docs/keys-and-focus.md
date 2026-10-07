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

## The quit key

`View(layout, quit_key="q")` sets the quit key; `quit_key=None` turns it off. Typing `q`
into a focused text box types it rather than quitting.

Ctrl+C quits too (raising `KeyboardInterrupt`, as usual), except in a focused text box
with text selected, where it copies. Ctrl+Z, Ctrl+S, Ctrl+Q and Ctrl+V reach the app as
keys you can bind, rather than being taken by the terminal.
