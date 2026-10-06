from cmdgui import View, Popup, Label, Button, Menu, Stdout

class Confirm(Popup):
    """A dialog: blocks everything else until you answer (or press Escape)."""
    layout = """
        message  -
        yes      no
    """
    title = "Clear the log?"
    message = Label("This can't be undone.", align="center")
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

def clear_log():
    view.log.clear()
    view.confirm.close()

class App(View):
    layout = """
        clear  pick  about  .
        log    -     -      -
    """
    clear = Button("Clear log", on_click=lambda: view.show(view.confirm))
    pick = Button("Pick fruit", on_click=lambda: view.show(view.fruit, below=view.pick))
    about = Button("About", on_click=lambda: view.alert("Popups float over the layout.\nTab, Enter and Escape work in them.", title="About"))
    log = Stdout()

    confirm = Confirm()
    fruit = Fruit()

view = App()
view.confirm.yes.on_click(clear_log)
view.confirm.on_close(lambda: print("dialog closed"))

for line in ["Click the buttons above.", "Escape closes a popup.", "Press q to quit."]:
    print(line)
view.wait()
