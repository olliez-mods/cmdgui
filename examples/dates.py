from cmdgui import View, Calendar, DatePicker, Label, Text, style
from datetime import date, timedelta

# Pick days. The calendar: click a day, or arrows and Enter when focused, Page Up/Down
# or the ‹ › arrows (or scrolling) for other months. The date pickers open a calendar
# when clicked (or Enter); up/down change them by a day. q to quit.

today = date.today()

def stay_changed(_day):
    start, end = view.check_in.value, view.check_out.value
    if start and end:
        nights = (end - start).days
        view.summary.text = f"staying {nights} night{'s' if nights != 1 else ''}"
    # Can't leave before arriving
    if start:
        view.check_out.min_date = start + timedelta(days=1)
        if end and end <= start: view.check_out.choose(start + timedelta(days=1))

class Booking(View):
    layout = """
        month   check_in
        |       check_out
        |       summary
        |       help
        picked  -
    """
    month = Calendar(title="calendar", first_weekday=6,  # weeks start on Sunday
                     on_change=lambda day: view.picked.set(text=f"moved to {day:%A %d %B}"),
                     on_select=lambda day: view.picked.set(text=f"picked {day:%A %d %B %Y}"))
    check_in = DatePicker(today, title="check in", border=True, min_date=today, format="%a %d %b %Y",
                          first_weekday=6, on_change=stay_changed)
    check_out = DatePicker(today + timedelta(days=3), title="check out", border=True, format="%a %d %b %Y",
                           first_weekday=6, on_change=stay_changed)
    summary = Label()
    help = Text("Check in can't be before today, and check out moves to stay after it.",
                style=style(fg="bright_black"))
    picked = Label("click a day")

view = Booking()
stay_changed(None)
view.focus(view.month)
view.wait()
