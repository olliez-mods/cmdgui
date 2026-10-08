import json
import tempfile
from pathlib import Path
from cmdgui import (View, Panel, Tabs, TextInput, RadioGroup, Slider, Toggle, Select, DatePicker,
                    Button, Label, KeyHints)

# A settings form. view.settings.values is everything in it as a dict (each tab a dict of
# its own), so saving is json.dump and loading is setting values back. on_values_change
# keeps the "unsaved changes" note up to date. Ctrl+S saves, q quits when not typing.

SAVED_FILE = Path(tempfile.gettempdir()) / "cmdgui_form_example.json"

class Profile(Panel):
    layout = """
        intro  -
        name   email
        city   .
    """
    intro = Label("[dim]Who you are. Labels and buttons aren't in the values, only inputs.[/]")
    name = TextInput(title="name", border=True)
    email = TextInput(title="email", placeholder="you@example.com", border=True)
    city = Select(["London", "Helsinki", "New York", "Haarlem"], title="city", border=True)

class Preferences(Panel):
    layout = """
        intro   -
        look    size
        emails  starts
    """
    intro = Label("[dim]How it looks. Dates are saved as text, and load back as dates.[/]")
    look = RadioGroup(["light", "dark", "system"], horizontal=True, title="look", border=True)
    size = Slider(12, min=8, max=20, step=1, title="text size", border=True)
    emails = Toggle("weekly emails")
    starts = DatePicker(title="starts", border=True)

class Settings(Tabs):
    profile = Profile(title="Profile")
    preferences = Preferences(title="Preferences")

def save():
    global saved
    saved = view.settings.values   # {"profile": {"name": ...}, "preferences": {...}}
    SAVED_FILE.write_text(json.dumps(saved, default=str, indent=2))  # dates as "2026-01-05"
    show_status()
    view.notify(f"Saved to {SAVED_FILE.name}", "ok")

def revert():
    view.settings.values = saved   # fills every input back in
    show_status()

def show_status(values=None):
    unsaved = view.settings.values != saved
    view.status.text = "[yellow]● unsaved changes[/]" if unsaved else "[green]✔ saved[/]"
    view.revert.enabled = unsaved

class App(View):
    layout = """
        settings  -       -
        status    save    revert
        hints     -       -
    """
    settings = Settings()
    status = Label()
    save = Button("Save  Ctrl+S", on_click=save)
    revert = Button("Revert", on_click=revert)
    hints = KeyHints()

view = App()
if SAVED_FILE.exists():
    view.settings.values = json.loads(SAVED_FILE.read_text())   # strings go back into dates too
saved = view.settings.values
view.settings.on_values_change(show_status)   # called with the values on every edit
view.on_key("ctrl+s", save, "Save")
show_status()
view.wait()
