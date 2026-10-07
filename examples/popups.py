import itertools
from cmdgui import View, Popup, Label, Button, Menu, Stdout

class Confirm(Popup):
    """A dialog: blocks everything else until you answer (or press Escape)."""
    layout = """
        message  -
        yes      no
    """
    title = "Clear the log?"
    message = Label("[bold]This can't be undone.[/]", align="center")
    yes = Button("Clear")
    no = Button("Cancel")

    def init(self):
        self.no.on_click(self.close)

class Fruit(Popup):
    """A dropdown: clicking anywhere else closes it, and the click still goes through."""
    picker = Menu(["apple", "banana", "cherry", "dragonfruit"],
                  on_select=lambda i, item: (print(f"picked {item}"), view.fruit.close()))
    modal = False
    close_on_outside_click = True
    preferred_width = 20      # wider than the items need; sizes work as for widgets ("20+", "20-30")

NOTES = itertools.cycle([("Saved [bold]notes.txt[/]", "ok"), ("3 new messages", "info"),
                         ("Battery at 10%, plug in soon so you don't lose your work", "warning"),
                         ("Couldn't reach the server", "error")])

def notify():
    """A notification: it shows in the corner for a few seconds and doesn't get in the way.
    Click one to dismiss it."""
    message, level = next(NOTES)
    view.notify(message, level)

def clear_log():
    view.log.clear()
    view.confirm.close()

class App(View):
    layout = """
        clear  pick  about  toast  .
        log    -     -      -      -
    """
    clear = Button("Clear log", on_click=lambda: view.show(view.confirm))
    pick = Button("Pick fruit", on_click=lambda: view.show(view.fruit, below=view.pick))
    about = Button("About", on_click=lambda: view.alert("[bold]Popups[/] float over the layout.\n[dim]Tab, Enter and Escape work in them.[/]", title="About"))
    toast = Button("Notify", on_click=notify)
    log = Stdout()

    confirm = Confirm()
    fruit = Fruit()

view = App()
view.confirm.yes.on_click(clear_log)
view.confirm.on_close(lambda: print("dialog closed"))

for line in ["Click the buttons above.", "Escape closes a popup.", "Press q to quit."]:
    print(line)
view.wait()
