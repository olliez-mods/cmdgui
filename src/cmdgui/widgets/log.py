from __future__ import annotations

import logging
import re
import threading
import time as _time
from datetime import datetime
from typing import TYPE_CHECKING, Literal, Optional, Union
from ..shorts import *
from .. import clipboard
from .base import Widget

Level = Literal["debug", "info", "warning", "error", "critical"]
LEVELS = {"debug": 10, "info": 20, "warning": 30, "error": 40, "critical": 50} # the same numbers as logging's
LABELS = {"debug": "DEBUG", "info": "INFO", "warning": "WARN", "error": "ERROR", "critical": "CRIT"}
LABEL_WIDTH = 5


def _level_name(level):
    """A level name from a name ("warn" and any case work) or a logging number."""
    if isinstance(level, int) and not isinstance(level, bool):
        return next((name for name, number in reversed(LEVELS.items()) if level >= number), "debug")
    name = str(level).lower()
    name = {"warn": "warning", "fatal": "critical", "err": "error"}.get(name, name)
    if name not in LEVELS:
        raise ValueError(f"unknown log level {level!r}: use {', '.join(map(repr, LEVELS))}")
    return name


class Log(Widget):
    """Log messages, each with a level shown in colour, and a time. Hide the less
    important ones with level, and find messages with search. Scroll with the mouse
    wheel, or the arrow keys, Page Up/Down and Home/End when focused; End follows new
    messages again.

        log = Log()
        log.info("started")
        log.error("couldn't connect", "to", host)
        logging.getLogger().addHandler(log.handler())   # Python's logging, too

    Safe to add to from any thread."""
    level: Level = "debug" # hide messages less important than this
    search: str = ""       # show only messages containing this (ignoring case), highlighted
    show_time: bool = True
    time_format: str = "%H:%M:%S" # for strftime
    max_entries: int = 1000 # the oldest messages are dropped after this many
    markup: bool = False # read [style]...[/] in messages (off, as they often hold data with [ in it)
    border = True
    preferred_width = "10+"
    preferred_height = "3+"
    focusable = True

    def init(self):
        self._entries: list[tuple[float, str, str]] = [] # (time, level, message)
        self._lock = threading.Lock() # for _entries; never held while taking another lock
        self.scroll = 0 # rows up from the bottom

    if not TYPE_CHECKING:
        def __setattr__(self, key, value):
            if key == "level":
                value = _level_name(value)
            elif key == "search":
                value = str(value or "")
            super().__setattr__(key, value)
            if key in ("level", "search"): self._set_scroll(0) # different messages now: back to the newest

    @property
    def entries(self) -> list[tuple[datetime, str, str]]:
        """Every message kept, shown or not, oldest first: (time, level, message)."""
        with self._lock:
            return [(datetime.fromtimestamp(t), level, message) for t, level, message in self._entries]

    def add(self, *values, level: Union[Level, int] = "info", time: Union[float, datetime, None] = None,
            sep: str = " ") -> None:
        """Add a message. values are joined like print() does. level is a name or a
        logging level number; time a datetime or timestamp, or None for now."""
        level = _level_name(level)
        if isinstance(time, datetime): time = time.timestamp()
        entry = (_time.time() if time is None else float(time), level, sep.join(map(str, values)))
        with self._lock:
            self._entries.append(entry)
            del self._entries[:-max(1, self.max_entries)]
        if self.scroll and self._shows(entry): # stay put while scrolled up
            self._set_scroll(self.scroll + len(self._entry_rows(entry, self.width)))
        self.refresh()

    def debug(self, *values, sep: str = " "): self.add(*values, level="debug", sep=sep)
    def info(self, *values, sep: str = " "): self.add(*values, level="info", sep=sep)
    def warning(self, *values, sep: str = " "): self.add(*values, level="warning", sep=sep)
    def error(self, *values, sep: str = " "): self.add(*values, level="error", sep=sep)
    def critical(self, *values, sep: str = " "): self.add(*values, level="critical", sep=sep)

    def clear(self) -> None:
        """Remove every message."""
        with self._lock:
            self._entries.clear()
        self._set_scroll(0)
        self.refresh()

    def count(self, level: Union[Level, int, None] = None) -> int:
        """How many messages there are at a level, or in all."""
        name = None if level is None else _level_name(level)
        with self._lock:
            return sum(1 for entry in self._entries if name is None or entry[1] == name)

    def handler(self, level: Union[Level, int] = logging.NOTSET) -> logging.Handler:
        """A handler that sends Python's logging here:
            logging.getLogger().addHandler(log.handler())
        Only the message is shown; give it a formatter for more, e.g.
        handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))."""
        number = level if isinstance(level, int) else LEVELS[_level_name(level)]
        return _Handler(self, number)

    # --- Drawing ---
    def _set_scroll(self, value):
        object.__setattr__(self, "scroll", value) # no redraw, the caller does that

    def _plain(self, message):
        return strip_markup(message) if self.markup else message

    def _shows(self, entry):
        _, level, message = entry
        return LEVELS[level] >= LEVELS[self.level] and (not self.search or self.search.lower() in self._plain(message).lower())

    def _prefix_width(self, width):
        """Columns before the message: the time (if there's room) and the level."""
        label = LABEL_WIDTH + 1
        clock = text_width(_time.strftime(self.time_format)) + 1 if self.show_time else 0
        return label + clock if width - label - clock >= 10 else label

    def _entry_rows(self, entry, width):
        """The rows an entry takes, as (start, end) of its message."""
        return wrap_spans(self._plain(entry[2]), width - self._prefix_width(width))

    def _entry_at(self, y):
        """The entry shown on row y, worked out as draw() does, or None."""
        with self._lock:
            entries = list(self._entries)
        rows = []
        for entry in reversed(entries):
            if(not self._shows(entry)): continue
            rows.extend([entry] * len(self._entry_rows(entry, self.width)))
            if(len(rows) >= self.scroll + self.height): break
        shown = list(reversed(rows[self.scroll:self.scroll + self.height]))
        return shown[y] if 0 <= y < len(shown) else None
    def menu_context(self, x, y):
        context = super().menu_context(x, y)
        entry = self._entry_at(y)
        context.update(line=self._plain(entry[2]) if entry else None, level=entry[1] if entry else None)
        return context
    def _default_menu_items(self, context):
        line = context["line"]
        return [("Copy line", lambda ctx: clipboard.copy(line), lambda ctx: 1 if line is not None else 0),
                ("Clear", lambda ctx: self.clear(), None)]
    def key_hints(self):
        return [("up/down", "Scroll")]

    def on_input(self, input):
        if(input.type == "mouse_scroll" and self.mouse_over()):
            step = 1 if input.details["direction"] == "up" else -1
            self._set_scroll(max(0, self.scroll + step))
            self.refresh()
        elif(input.type == "key"):
            page = max(1, self.height - 1)
            moves = {"up": 1, "down": -1, "page_up": page, "page_down": -page,
                     "home": 10 ** 9, "end": -10 ** 9} # draw() stops it at the top
            if(input.details["key"] in moves):
                self._set_scroll(max(0, self.scroll + moves[input.details["key"]]))
                self.refresh()

    def draw(self, c):
        with self._lock:
            entries = list(self._entries)
        # Wrap from the newest back, only as far as needed
        need, rows = self.scroll + c.height, [] # (entry, start, end, first row of the entry), newest first
        for entry in reversed(entries):
            if(not self._shows(entry)): continue
            spans = self._entry_rows(entry, c.width)
            rows.extend((entry, start, end, i == 0) for i, (start, end) in reversed(list(enumerate(spans))))
            if(len(rows) >= need): break
        else:
            self._set_scroll(min(self.scroll, max(0, len(rows) - c.height))) # reached the oldest
        if(not rows):
            note = "no messages match" if entries else "no messages yet"
            c.text(0, 0, fit(note, c.width), self.theme("dim"))
            return

        prefix = self._prefix_width(c.width)
        pattern = re.compile(re.escape(self.search), re.IGNORECASE) if self.search else None
        shown = rows[self.scroll:self.scroll + c.height]
        for y, (entry, start, end, first) in enumerate(reversed(shown)):
            when, level, message = entry
            if(first):
                x = 0
                if(prefix > LABEL_WIDTH + 1):
                    x = c.text(0, y, _time.strftime(self.time_format, _time.localtime(when)), self.theme("dim")) + 1
                c.text(x, y, LABELS[level], self.theme("log_" + level))
            s = self.theme("error") if LEVELS[level] >= LEVELS["error"] else ""
            plain, styles = parse_markup(message, s) if self.markup else (message, [s] * len(message))
            matches = [m.span() for m in pattern.finditer(plain)] if pattern else [] # whole message, for matches split across rows
            x = prefix
            for i in range(start, end):
                hit = any(a <= i < b for a, b in matches)
                x += c.put(x, y, plain[i], self.theme("match") if hit else styles[i])
        if(self.scroll):
            label = f" ↓ {self.scroll} more "
            c.text(max(0, c.width - len(label)), c.height - 1, label, self.theme("dim"))

    def content_size(self):
        return 50, 8


class _Handler(logging.Handler):
    def __init__(self, log, level):
        super().__init__(level)
        self.log = log

    def emit(self, record):
        try:
            if self.formatter:
                message = self.format(record)
            else:
                message = record.getMessage()
                if record.exc_info:
                    message += "\n" + logging.Formatter().formatException(record.exc_info)
            self.log.add(message, level=record.levelno, time=record.created)
        except Exception:
            self.handleError(record)
