from __future__ import annotations

from typing import Any, Callable, Optional, Union
from ..shorts import *
from ..inputs import mouse
from .. import clipboard
from .base import Widget, field, _call, Align

def _styled(widget, text, base):
    """(plain text, a style per character) for text, read as markup if the widget's
    markup setting is on."""
    text = str(text)
    return parse_markup(text, base) if widget.markup else (text, [base] * len(text))


class Text(Widget):
    """Text that wraps to fit. Style parts of it with markup:
    "[bold red]Error:[/] couldn't open [cyan]notes.txt[/]"."""
    text: str = field(default="", kw_only=False)
    align: Align = "left"
    style: str = "" # escape code from style(), e.g. style(fg="red")
    markup: bool = True # read [style]...[/] in the text; False shows it as it is
    def draw(self, c):
        base = self.style or self.theme("text")
        plain, styles = _styled(self, self.text, base)
        for i, (start, end) in enumerate(wrap_spans(plain, c.width)[:c.height]):
            c.styled(0, i, plain[start:end], styles[start:end], base, c.width, self.align)
    def content_size(self):
        plain = _styled(self, self.text, "")[0]
        width = min(80, max(text_width(line) for line in plain.split("\n")))
        return width, max(1, len(wrap_spans(plain, width)))


class Label(Text):
    """One line of text, cut off with … if too long."""
    preferred_height = 1
    def draw(self, c):
        base = self.style or self.theme("text")
        plain, styles = _styled(self, self.text, base)
        c.styled(0, c.height // 2, plain, styles, base, c.width, self.align)
    def content_size(self):
        return text_width(_styled(self, self.text, "")[0]), 1


def _is_word(char):
    return char.isalnum() or char == "_"

def _word_left(text, i):
    """Where Ctrl+Left goes from i: the start of the word before it."""
    while i > 0 and not _is_word(text[i - 1]): i -= 1
    while i > 0 and _is_word(text[i - 1]): i -= 1
    return i

def _word_right(text, i):
    """Where Ctrl+Right goes from i: the end of the word after it."""
    while i < len(text) and not _is_word(text[i]): i += 1
    while i < len(text) and _is_word(text[i]): i += 1
    return i

def _index_at(text, start, end, x):
    """The index in text[start:end] that's drawn at column x (wide characters take two)."""
    col = 0
    for i in range(start, end):
        col += char_width(text[i])
        if col > x: return i
    return end

# Keys that only move the cursor; with Shift they select
MOVES = {"left", "right", "ctrl+left", "ctrl+right", "alt+left", "alt+right", "alt+b", "alt+f",
         "home", "end", "ctrl+a", "ctrl+e"}

def _clean(text, newlines):
    """Pasted text, without control characters. Tabs become spaces, and so do newlines
    unless newlines is True."""
    text = text.replace("\t", "    ")
    if not newlines: text = " ".join(line for line in text.split("\n") if line)
    return "".join(ch for ch in text if ch == "\n" or ch.isprintable())

def _edit(value, cursor, key, char, line_start, line_end):
    """The editing keys both text boxes share. Returns the new (value, cursor),
    or None if the key isn't one of them. line_start/line_end bound the cursor's line."""
    if(char): return value[:cursor] + char + value[cursor:], cursor + 1
    if(key == "backspace"):
        return (value[:cursor - 1] + value[cursor:], cursor - 1) if cursor > 0 else (value, cursor)
    if(key == "delete"): return value[:cursor] + value[cursor + 1:], cursor
    if(key == "left"): return value, max(0, cursor - 1)
    if(key == "right"): return value, min(len(value), cursor + 1)
    if(key in ("ctrl+left", "alt+left", "alt+b")): return value, _word_left(value, cursor)
    if(key in ("ctrl+right", "alt+right", "alt+f")): return value, _word_right(value, cursor)
    if(key in ("home", "ctrl+a")): return value, line_start
    if(key in ("end", "ctrl+e")): return value, line_end
    if(key in ("ctrl+w", "alt+backspace")): # delete the word before the cursor
        new = _word_left(value, cursor)
        return value[:new] + value[cursor:], new
    if(key == "ctrl+u"): return value[:line_start] + value[cursor:], line_start # delete to the start of the line
    if(key == "ctrl+k"): return value[:cursor] + value[line_end:], cursor        # delete to the end of the line
    return None


class _Editable:
    """Selection, clipboard and the shared editing keys, for TextInput and TextArea.
    Uses self.value, self.cursor and self.change_callback."""
    def _init_editing(self):
        self.anchor: Optional[int] = None # the other end of the selection from the cursor, if any
        self._selecting = False # dragging out a selection with the mouse

    @property
    def selection(self) -> Optional[tuple[int, int]]:
        """(start, end) of the selected text, or None."""
        if self.anchor is None: return None
        anchor, cursor = min(self.anchor, len(self.value)), min(self.cursor, len(self.value))
        return (min(anchor, cursor), max(anchor, cursor)) if anchor != cursor else None

    @property
    def selected_text(self) -> str:
        sel = self.selection
        return self.value[sel[0]:sel[1]] if sel else ""

    def select(self, start: int, end: int) -> None:
        """Select value[start:end], with the cursor at end."""
        self.anchor, self.cursor = max(0, start), max(0, min(end, len(self.value)))

    def select_all(self) -> None:
        self.select(0, len(self.value))

    def _secret(self):
        return getattr(self, "password", False) # passwords can't be copied

    def _claims_key(self, key):
        return key == "ctrl+c" and self.selection is not None and not self._secret()

    def _set_text(self, value, cursor):
        """Change the text (dropping the selection), calling on_change if it changed."""
        changed = value != self.value
        self.anchor = None
        self.value, self.cursor = value, cursor
        if(changed): _call(self.change_callback, self.value)

    def _insert(self, text):
        """Type or paste text, in place of the selection if there is one."""
        start, end = self.selection or (self.cursor, self.cursor)
        self._set_text(self.value[:start] + text + self.value[end:], start + len(text))

    def _move(self, cursor, selecting):
        """Move the cursor; selecting (Shift held) keeps the other end of the selection where it was."""
        if(selecting):
            if(self.anchor is None): self.anchor = self.cursor
        else:
            self.anchor = None
        self.cursor = cursor

    def _edit_key(self, key, char, line_start, line_end):
        """Handle an editing key. Returns False if it isn't one."""
        value, cursor, sel = self.value, self.cursor, self.selection
        if(key in ("ctrl+c", "ctrl+x")):
            if(sel and not self._secret()):
                clipboard.copy(value[sel[0]:sel[1]])
                if(key == "ctrl+x"): self._set_text(value[:sel[0]] + value[sel[1]:], sel[0])
            return True
        if(key == "ctrl+v"):
            self._insert(_clean(clipboard.paste(), isinstance(self, TextArea)))
            return True
        if(char):
            self._insert(char)
            return True
        if(sel and key in ("backspace", "delete")):
            self._set_text(value[:sel[0]] + value[sel[1]:], sel[0])
            return True
        selecting = "shift+" in key
        base = key.replace("shift+", "")
        if(base in MOVES):
            if(sel and not selecting and base in ("left", "right")):
                self._move(sel[0] if base == "left" else sel[1], False) # to that end of the selection
            else:
                self._move(_edit(value, cursor, base, None, line_start, line_end)[1], selecting)
            return True
        result = _edit(value, cursor, key, None, line_start, line_end)
        if(result is None): return False
        self._set_text(*result)
        return True

    def _mouse_select(self, input, index_at_mouse):
        """Click to put the cursor, drag to select. Returns True if it used the input."""
        if(input.type == "mouse_down" and input.details["button"] == 0 and self.mouse_over()):
            index = index_at_mouse()
            self.anchor, self.cursor, self._selecting = index, index, True
            return True
        if(input.type == "mouse_move" and self._selecting and mouse.is_down(0)):
            self.cursor = index_at_mouse() # keeps following the mouse outside the box
            return True
        if(input.type in ("mouse_up", "mouse_move") and self._selecting):
            self._selecting = False
            if(self.anchor == self.cursor): self.anchor = None
            elif(getattr(self.view, "copy_on_select", False) and not self._secret()):
                clipboard.copy(self.selected_text) # like a terminal's copy on select
            return True
        return False


class TextInput(_Editable, Widget):
    """A one-line text box. Click or Tab to it, then type. Drag or Shift+arrows to
    select, Ctrl+C / Ctrl+X / Ctrl+V to copy, cut and paste."""
    value: str = field(default="", kw_only=False)
    placeholder: str = ""      # shown while it's empty and not focused
    prefix: str = ""           # shown dim before the text, but not part of it, e.g. "https://"
    suffix: str = ""           # shown dim after the text, e.g. " kg"
    suggest: Union[list, Callable[[str], Optional[str]], None] = None # completions: see below
    password: bool = False     # show • instead of the text
    keep_history: bool = False # Enter remembers the value, and up/down bring back earlier ones
    submit_callback: Optional[Callable[[str], Any]] = field(default=None, alias="on_submit")
    change_callback: Optional[Callable[[str], Any]] = field(default=None, alias="on_change")
    preferred_width = "5+"
    preferred_height = 1
    border = True
    focusable = True
    captures_text = True
    def init(self):
        self.cursor = 0 # index in value
        self.scroll = 0 # first visible character, when the value is longer than the box
        self.history = [] # submitted values, oldest first (with keep_history)
        self._history_index = None # which one up/down is showing, None while editing a new value
        self._draft = "" # the new value, kept while looking through the history
        self._init_editing()
    def on_submit(self, callback: Callable[[str], Any]): # called with the value when Enter is pressed
        self.submit_callback = callback
    def on_change(self, callback: Callable[[str], Any]): # called with the value after every edit
        self.change_callback = callback

    @property
    def suggestion(self) -> Optional[str]:
        """The completion shown for what's typed, from suggest: a list (the first item that
        starts with the text, ignoring case), or a function given the text that returns
        the whole suggested value or None."""
        if(not self.value or self.password or not self.suggest): return None
        if(callable(self.suggest)):
            found = self.suggest(self.value)
        else:
            lower = self.value.lower()
            found = next((str(item) for item in self.suggest if str(item).lower().startswith(lower)), None)
        if(not found or len(found) <= len(self.value) or found[:len(self.value)].lower() != self.value.lower()):
            return None # nothing more to add
        return found
    def _ghost(self):
        """The rest of the suggestion, shown dim after the cursor, while at the end of the text."""
        found = self.suggestion if self.focused and self.cursor >= len(self.value) and not self.selection else None
        return found[len(self.value):] if found else ""
    def accept_suggestion(self) -> bool:
        """Fill in the suggestion. Returns False if there wasn't one."""
        found = self.suggestion
        if(not found): return False
        self._set_text(found, len(found))
        return True

    def _shown(self):
        return "•" * len(self.value) if self.password else self.value
    def _set_text(self, value, cursor):
        self._history_index = None # an edit: no longer looking through the history
        super()._set_text(value, cursor)
    def _recall(self, step):
        """Up (-1) or down (+1) through the history."""
        if(not self.keep_history or not self.history): return
        if(self._history_index is None):
            if(step > 0): return
            self._draft = self.value
            index = len(self.history) - 1
        else:
            index = max(0, self._history_index + step)
        if(index >= len(self.history)):
            index, value = None, self._draft # past the newest: back to what was being typed
        else:
            value = self.history[index]
        super()._set_text(value, len(value))
        self._history_index = index
    def _claims_key(self, key):
        return super()._claims_key(key) or (key == "tab" and bool(self._ghost())) # Tab accepts the suggestion
    def _index_at_mouse(self):
        x = self.mouse_pos()[0] - text_width(self.prefix)
        return _index_at(self._shown(), self.scroll, len(self.value), max(0, x))

    def on_input(self, input):
        if(input.type == "paste"):
            self._insert(_clean(input.details["text"], newlines=False))
            return
        if(input.type.startswith("mouse")):
            self._mouse_select(input, self._index_at_mouse)
            return
        if(input.type != "key"): return
        key, char = input.details["key"], input.details["char"]
        if(key == "enter"):
            if(self.keep_history and self.value and not self.password and self.history[-1:] != [self.value]):
                self.history.append(self.value)
            self._history_index = None
            _call(self.submit_callback, self.value)
        elif(key in ("up", "down")):
            self._recall(-1 if key == "up" else 1)
        elif(key in ("tab", "right", "end") and self._ghost()):
            self.accept_suggestion()
        else:
            self._edit_key(key, char, 0, len(self.value))

    def draw(self, c):
        shown = self._shown()
        self.cursor = max(0, min(self.cursor, len(shown)))
        if(not self.value and not self.focused):
            c.text(0, 0, fit(self.placeholder, c.width), self.theme("dim"))
            return
        dim = self.theme("dim")
        left = c.text(0, 0, fit(self.prefix, c.width), dim) if self.prefix else 0
        room = max(1, c.width - left - text_width(self.suffix)) # for the text itself
        # Keep the cursor in view, counting columns (wide characters take two)
        if(self.cursor < self.scroll): self._set_scroll(self.cursor)
        cursor_width = char_width(shown[self.cursor]) if self.cursor < len(shown) else 1
        while(self.scroll < self.cursor and text_width(shown[self.scroll:self.cursor]) + cursor_width > room):
            self._set_scroll(self.scroll + 1)
        sel = self.selection
        x = left
        for i in range(self.scroll, len(shown)):
            if(x + char_width(shown[i]) > left + room): break
            x += c.put(x, 0, shown[i], self.theme("selection") if sel and sel[0] <= i < sel[1] else "")
        ghost = self._ghost()
        if(ghost): x = c.text(x, 0, take(ghost, max(0, left + room - x)), dim)
        if(self.suffix): # after the text, and after the cursor if it's at the end
            c.text(x + (1 if self.focused and self.cursor >= len(shown) and not ghost else 0), 0, self.suffix, dim)
        if(self.focused):
            under = shown[self.cursor] if self.cursor < len(shown) else (ghost[:1] or " ")
            c.put(left + text_width(shown[self.scroll:self.cursor]), 0, under, self.theme("cursor"))
    def _set_scroll(self, value):
        object.__setattr__(self, "scroll", value) # no redraw, we're already drawing
    def content_size(self):
        return max(20, text_width(self.placeholder) + 1, text_width(self.prefix + self.suffix) + 10), 1


class TextArea(_Editable, Widget):
    """A multi-line text box. Long lines wrap. Enter adds a new line. Drag or
    Shift+arrows to select, Ctrl+C / Ctrl+X / Ctrl+V to copy, cut and paste."""
    value: str = field(default="", kw_only=False)
    placeholder: str = ""
    change_callback: Optional[Callable[[str], Any]] = field(default=None, alias="on_change")
    preferred_width = "10+"
    preferred_height = "3+"
    border = True
    focusable = True
    captures_text = True
    def init(self):
        self.cursor = 0 # index in value
        self.scroll = 0 # first visible (wrapped) row
        self._follow = True # scroll to the cursor on the next draw
        self._init_editing()
    def on_change(self, callback: Callable[[str], Any]): # called with the value after every edit
        self.change_callback = callback

    def _rows(self, width):
        """The wrapped rows as (start, end) indexes into value. A line that exactly fills
        its last row gets an extra empty row, so the cursor has somewhere to go."""
        rows, start, width = [], 0, max(1, width)
        for line in self.value.split("\n"):
            row_start, col = 0, 0
            for i, char in enumerate(line):
                w = char_width(char)
                if(col + w > width and i > row_start): # doesn't fit: start a new row
                    rows.append((start + row_start, start + i))
                    row_start, col = i, 0
                col += w
            rows.append((start + row_start, start + len(line)))
            if(line and col >= width):
                rows.append((start + len(line), start + len(line)))
            start += len(line) + 1
        return rows
    def _cursor_row(self, rows):
        """Which row the cursor is on, and its column in that row."""
        for i, (start, end) in enumerate(rows):
            next_start = rows[i + 1][0] if i + 1 < len(rows) else None
            if start <= self.cursor <= end and next_start != self.cursor:
                return i, text_width(self.value[start:self.cursor])
        return len(rows) - 1, 0
    def _index_at_mouse(self):
        rows = self._rows(self.width)
        x, y = self.mouse_pos()
        start, end = rows[max(0, min(len(rows) - 1, self.scroll + y))]
        return _index_at(self.value, start, end, max(0, x))

    def on_input(self, input):
        if(input.type == "mouse_scroll" and self.mouse_over()):
            step = -1 if input.details["direction"] == "up" else 1
            self.scroll = max(0, min(len(self._rows(self.width)) - self.height, self.scroll + step))
            return
        if(input.type == "paste"):
            self._follow = True
            self._insert(_clean(input.details["text"], newlines=True))
            return
        if(input.type.startswith("mouse")):
            if(self._mouse_select(input, self._index_at_mouse)): self._follow = True
            return
        if(input.type != "key"): return
        key, char = input.details["key"], input.details["char"]
        value, cursor = self.value, self.cursor
        line_start = value.rfind("\n", 0, cursor) + 1
        line_end = value.find("\n", cursor) % (len(value) + 1) # -1 (last line) becomes len(value)
        base = key.replace("shift+", "")
        self._follow = True
        if(key == "enter"):
            self._insert("\n")
        elif(base in ("up", "down", "page_up", "page_down")):
            rows = self._rows(self.width)
            row, x = self._cursor_row(rows)
            step = {"up": -1, "down": 1, "page_up": -self.height, "page_down": self.height}[base]
            start, end = rows[max(0, min(len(rows) - 1, row + step))]
            self._move(_index_at(value, start, end, x), "shift+" in key)
        elif(base in ("ctrl+home", "ctrl+end")):
            self._move(0 if base == "ctrl+home" else len(value), "shift+" in key)
        else:
            self._edit_key(key, char, line_start, line_end)

    def draw(self, c):
        self.cursor = max(0, min(self.cursor, len(self.value)))
        rows = self._rows(c.width)
        row, x = self._cursor_row(rows)
        if(self._follow): # keep the cursor in view
            if(row < self.scroll): self._set_scroll(row)
            if(row >= self.scroll + c.height): self._set_scroll(row - c.height + 1)
            self._follow = False
        self._set_scroll(max(0, min(self.scroll, len(rows) - c.height)))
        if(not self.value and not self.focused):
            for i, line in enumerate(wrap(self.placeholder, c.width)[:c.height]):
                c.text(0, i, line, self.theme("dim"))
            return
        sel = self.selection
        for i, (start, end) in enumerate(rows[self.scroll:self.scroll + c.height]):
            if(sel and sel[0] <= end and sel[1] > start):
                col = 0
                for j in range(start, end):
                    col += c.put(col, i, self.value[j], self.theme("selection") if sel[0] <= j < sel[1] else "")
                if(sel[0] <= end < sel[1] and end < len(self.value)): # the selection goes on past this row
                    c.put(col, i, " ", self.theme("selection"))
            else:
                c.text(0, i, self.value[start:end])
        if(self.focused and self.scroll <= row < self.scroll + c.height):
            char = self.value[self.cursor] if self.cursor < len(self.value) and self.value[self.cursor] != "\n" else " "
            c.put(x, row - self.scroll, char, self.theme("cursor"))
    def _set_scroll(self, value):
        object.__setattr__(self, "scroll", value) # no redraw, we're already drawing
    def content_size(self):
        return 30, 5
