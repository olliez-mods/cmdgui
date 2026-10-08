from __future__ import annotations

import calendar
import datetime
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Callable, Optional
from ..shorts import *
from .base import Widget, field, _call

GRID_WIDTH = 20 # 7 days, 2 columns each with a space between
WEEKS = 6       # always 6 rows, so the height doesn't change from month to month


def _as_date(value):
    """A date, from a date or datetime (or None)."""
    if value is None: return None
    if isinstance(value, datetime.datetime): return value.date()
    if isinstance(value, date): return value
    raise TypeError(f"expected a date, got {type(value).__name__}")


def _add_months(day, months):
    """The same day of another month, or that month's last day if it's shorter."""
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    return day.replace(year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1]))


class Calendar(Widget):
    """A month of days to pick from. Click a day, or move with the arrow keys
    (Page Up/Down for the month before or after) and press Enter. Click the arrows
    either side of the month's name, or scroll, to change month."""
    value: Optional[date] = field(default=None, kw_only=False) # the chosen day
    min_date: Optional[date] = None # days before this can't be chosen
    max_date: Optional[date] = None
    first_weekday: int = 0 # 0 for Monday, 6 for Sunday
    change_callback: Optional[Callable[[date], Any]] = field(default=None, alias="on_change")
    select_callback: Optional[Callable[[date], Any]] = field(default=None, alias="on_select")
    preferred_width = f"{GRID_WIDTH}+"
    preferred_height = WEEKS + 2
    border = True
    focusable = True

    def init(self):
        today = date.today()
        self.month = (today.year, today.month) # the month shown, (year, month)
        self.hovered: Optional[date] = None

    if not TYPE_CHECKING:
        def __setattr__(self, key, value):
            if key in ("value", "min_date", "max_date"):
                value = _as_date(value)
            super().__setattr__(key, value)
            if key == "value" and value is not None and (value.year, value.month) != self.month:
                self.month = (value.year, value.month) # show the chosen day's month

    def on_change(self, callback: Callable[[date], Any]): # called with the date whenever the chosen day changes
        self.change_callback = callback
    def on_select(self, callback: Callable[[date], Any]): # called with the date on Enter or a click
        self.select_callback = callback

    def allowed(self, day: date) -> bool:
        """True if day is between min_date and max_date."""
        return (self.min_date is None or day >= self.min_date) and (self.max_date is None or day <= self.max_date)

    def choose(self, day: date) -> None:
        """Set the chosen day (kept between min_date and max_date), calling on_change if it moved."""
        day = _as_date(day)
        if self.min_date is not None: day = max(day, self.min_date)
        if self.max_date is not None: day = min(day, self.max_date)
        if day != self.value:
            self.value = day
            _call(self.change_callback, day)

    def show_month(self, year: int, month: int) -> None:
        """Show a month without changing the chosen day. Months past 12 (or below 1)
        go into the next (or previous) year."""
        year, month = divmod(year * 12 + month - 1, 12)
        self.month = (year, month + 1)

    def _step_month(self, months):
        year, month = self.month
        self.show_month(year, month + months)

    def _weeks(self):
        """The shown month as 6 weeks of dates, with days from the months either side."""
        year, month = self.month
        weeks = calendar.Calendar(self.first_weekday % 7).monthdatescalendar(year, month)
        while len(weeks) < WEEKS:
            weeks.append([day + timedelta(days=7) for day in weeks[-1]])
        return weeks

    def _left(self):
        """Where the grid starts, centred in the widget."""
        return max(0, (self.width - GRID_WIDTH) // 2)

    def _day_at(self, x, y):
        """The date drawn at (x, y) in the widget, or None."""
        col, offset = divmod(x - self._left(), 3)
        if not (2 <= y < 2 + WEEKS and 0 <= col < 7 and offset < 2): return None
        return self._weeks()[y - 2][col]

    def key_hints(self):
        return [("up/down/left/right", "Move"), ("page_up/page_down", "Month"), ("enter", "Choose")]

    def on_input(self, input):
        if(input.type == "key"):
            key = input.details["key"]
            start = self.value or date.today()
            days = {"left": -1, "right": 1, "up": -7, "down": 7}
            if(key in days): self.choose(start + timedelta(days=days[key]))
            elif(key in ("page_up", "page_down")): self.choose(_add_months(start, -1 if key == "page_up" else 1))
            elif(key == "home"): self.choose(start.replace(day=1))
            elif(key == "end"): self.choose(start.replace(day=calendar.monthrange(start.year, start.month)[1]))
            elif(key in ("enter", "space")):
                if(self.value is None): self.choose(start)
                if(self.value is not None): _call(self.select_callback, self.value)
            return
        if(not input.type.startswith("mouse")): return
        x, y = self.mouse_pos()
        over = self._day_at(x, y) if self.mouse_over() else None
        if(over != self.hovered): self.hovered = over
        if(input.type == "mouse_scroll" and self.mouse_over()):
            self._step_month(-1 if input.details["direction"] == "up" else 1)
        elif(input.type == "mouse_down" and self.mouse_over()):
            left = self._left()
            if(y == 0 and x in (left, left + 1)): self._step_month(-1)
            elif(y == 0 and x in (left + GRID_WIDTH - 2, left + GRID_WIDTH - 1)): self._step_month(1)
            elif(over is not None and self.allowed(over)):
                self.choose(over)
                _call(self.select_callback, over)

    def draw(self, c):
        x0 = max(0, (c.width - GRID_WIDTH) // 2)
        year, month = self.month
        c.text(x0, 0, "‹", self.theme("dim"))
        c.text(x0 + 1, 0, pad_center(f"{calendar.month_name[month]} {year}", GRID_WIDTH - 2), self.theme("title"))
        c.text(x0 + GRID_WIDTH - 1, 0, "›", self.theme("dim"))
        names = " ".join(calendar.day_abbr[(self.first_weekday + i) % 7][:2] for i in range(7))
        c.text(x0, 1, names, self.theme("dim"))
        today = date.today()
        for row, week in enumerate(self._weeks()):
            for col, day in enumerate(week):
                if(day == self.value): s = self.theme("selected" if self.focused else "selected_unfocused")
                elif(day == self.hovered and self.allowed(day)): s = self.theme("hover")
                elif(day.month != month or not self.allowed(day)): s = self.theme("dim")
                elif(day == today): s = self.theme("today")
                else: s = ""
                c.text(x0 + 3 * col, 2 + row, f"{day.day:2}", s)

    def content_size(self):
        return GRID_WIDTH, WEEKS + 2


class DatePicker(Widget):
    """Shows a date, and opens a Calendar to pick one when clicked (or Enter/Space
    when focused). Up/down change it by a day without opening it."""
    value: Optional[date] = field(default=None, kw_only=False)
    placeholder: str = "pick a date" # shown when there's no date yet
    format: str = "%Y-%m-%d"         # how the date is shown, for strftime
    min_date: Optional[date] = None
    max_date: Optional[date] = None
    first_weekday: int = 0 # 0 for Monday, 6 for Sunday
    change_callback: Optional[Callable[[date], Any]] = field(default=None, alias="on_change")
    preferred_width = "5+"
    preferred_height = 1
    focusable = True

    def init(self):
        self.hovered = False
        self.dropdown = None # the open Popup, if any

    if not TYPE_CHECKING:
        def __setattr__(self, key, value):
            if key in ("value", "min_date", "max_date"):
                value = _as_date(value)
            super().__setattr__(key, value)

    def on_change(self, callback: Callable[[date], Any]): # called with the date when the user changes it
        self.change_callback = callback

    @property
    def is_open(self):
        return self.dropdown is not None and self.dropdown.is_open

    def choose(self, day: date) -> None:
        """Set the date (kept between min_date and max_date), calling on_change if it's different."""
        day = _as_date(day)
        if self.min_date is not None: day = max(day, self.min_date)
        if self.max_date is not None: day = min(day, self.max_date)
        if day != self.value:
            self.value = day
            _call(self.change_callback, day)

    def open(self):
        """Show a calendar below the widget (above if there's no room)."""
        if(self.view is None or self.is_open): return
        from ..view import Popup # here, because view.py imports the widgets
        picker = Calendar(self.value, min_date=self.min_date, max_date=self.max_date,
                          first_weekday=self.first_weekday, border=False, on_select=self._picked)
        self.dropdown = Popup(picker, close_on_outside_click=True, on_close=lambda: self.refresh())
        self.view.show(self.dropdown, below=self)
    def close(self):
        if(self.dropdown): self.dropdown.close()
    def _picked(self, day):
        self.close()
        self.choose(day)

    def key_hints(self):
        return [("enter", "Open"), ("up/down", "Day")]

    def on_input(self, input):
        if(input.type == "key"):
            key = input.details["key"]
            if(key in ("enter", "space", "alt+down")): self.open()
            elif(key in ("up", "down")): self.choose((self.value or date.today()) + timedelta(days=-1 if key == "up" else 1))
            return
        if(not input.type.startswith("mouse")): return
        if(self.mouse_over() != self.hovered):
            self.hovered = self.mouse_over()
        if(input.type == "mouse_down" and self.hovered):
            self.open()

    def _label(self):
        return self.placeholder if self.value is None else self.value.strftime(self.format)

    def draw(self, c):
        mid = c.height // 2
        s = self.theme("button_hover" if self.hovered else "button_focus" if self.focused or self.is_open else "button")
        inner = max(0, c.width - 5) # room between "[ " and " ▾]"
        x = c.text(0, mid, "[ ", s)
        c.text(x, mid, pad_right(fit(self._label(), inner), inner), self.theme("dim") if self.value is None else s)
        c.text(x + inner, mid, " ▾]", s)
    def content_size(self):
        sample = date(2000, 12, 28).strftime(self.format) # a long month name and day, for formats with names
        return max(text_width(sample), text_width(self.placeholder)) + 5, 1
