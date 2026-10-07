from cmdgui import View, Panel, Tabs, TextInput, Button, Checkbox, Slider, Stdout, Label

# Click a tab, or Ctrl+Page Up / Ctrl+Page Down from anywhere inside, q to quit.
# Each tab keeps what you typed, and where you were, while you're on another one.

class Profile(Panel):
    layout = """
        name   email
        save   .
    """
    name = TextInput(placeholder="your name")
    email = TextInput(placeholder="you@example.com")
    save = Button("Save", on_click=lambda: print(f"saved {view.settings.profile.name.value!r}"))

class Options(Panel):
    layout = """
        debug
        volume
    """
    debug = Checkbox("debug mode", on_change=lambda on: print("debug", on))
    volume = Slider(7, min=0, max=10, step=1, title="volume", border=True,
                    on_change=lambda value: print("volume", value))

class Settings(Tabs):
    profile = Profile()
    options = Options(title="Options")   # the title is what the tab bar shows
    log = Stdout()                       # any widget can be a tab, no panel needed; still collects prints while hidden

class App(View):
    layout = """
        settings
        status
    """
    settings = Settings(on_change=lambda name: view.status.set(
        text=f"showing the {name} tab ({type(view.settings.shown).__name__})"))
    status = Label("showing the profile tab (Profile)")

view = App()
view.focus(view.settings)   # start on the tab bar, so the keys work straight away
print("This is the log tab. Prints land here even while you're on another tab.")
view.wait()
