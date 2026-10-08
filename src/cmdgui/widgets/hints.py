from __future__ import annotations

from ..shorts import *
from .base import Widget

# How key names look in a footer
KEY_NAMES = {
    "up": "↑", "down": "↓", "left": "←", "right": "→", "enter": "Enter", "space": "Space",
    "escape": "Esc", "tab": "Tab", "shift_tab": "Shift+Tab", "backspace": "Bksp", "delete": "Del",
    "page_up": "PgUp", "page_down": "PgDn", "home": "Home", "end": "End",
}
ARROWS = "↑↓←→"


def key_name(key: str) -> str:
    """A key as a footer shows it: "ctrl+s" -> "Ctrl+S", "up/down" -> "↑↓",
    "ctrl+page_up/ctrl+page_down" -> "Ctrl+PgUp/PgDn"."""
    names, previous = [], None
    for part in [key] if len(key) == 1 else key.split("/"): # "/" itself is a key
        *mods, base = part.split("+") if part != "+" else [part]
        mods = "".join(f"{mod.capitalize()}+" for mod in mods)
        base = KEY_NAMES.get(base, base.upper() if len(base) == 1 and base.isalpha() and mods else base)
        if base[:1] == "f" and base[1:].isdigit(): base = base.upper() # f1 -> F1
        names.append(base if mods == previous else mods + base) # Ctrl+PgUp/PgDn: say the Ctrl+ once
        previous = mods
    return "".join(names) if all(name in ARROWS for name in names) else "/".join(names)


class KeyHints(Widget):
    """A footer of the keys that work right now: the focused widget's, Escape for an open
    popup, and your key bindings that have a label (view.on_key("ctrl+s", save, "Save")).
    It keeps up by itself as focus moves and popups open; put it in the layout, usually as
    the bottom row:

        layout = '''
            files  editor
            hints  -
        '''
        hints = KeyHints()"""
    separator: str = "   " # between one key and the next
    preferred_height = 1

    def draw(self, c):
        hints = self.view.key_hints() if self.view else []
        x = 0
        for key, label in hints:
            key, label = key_name(key), f" {label}"
            needed = text_width(key) + text_width(label)
            if x + needed > c.width:
                if x < c.width: c.text(min(x, c.width - 1), 0, "…", self.theme("hint"))
                break
            c.text(x, 0, key, self.theme("hint_key"))
            x += text_width(key)
            c.text(x, 0, label, self.theme("hint"))
            x += text_width(label) + text_width(self.separator)

    def content_size(self):
        return None, 1
