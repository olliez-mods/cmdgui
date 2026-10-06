import time
import cmdgui
from cmdgui import Label, TextInput, Menu, Popup

COMMANDS = {
    "help": lambda: print("Type anything and press Enter. Start with / for commands."),
    "time": lambda: print(time.strftime("%H:%M:%S")),
    "clear": lambda: view.stdout.clear(),
    "about": lambda: view.alert("A tiny cmdgui demo.\nEscape or OK closes this.", title="About"),
    "quit": lambda: view.quit(),
}

def enter_text(text):
    view.input.value = ""
    print(text)

def typed(value):
    # Typing "/" opens the command menu; keep typing to filter it
    if value.startswith("/"):
        matches = [name for name in COMMANDS if name.startswith(value[1:])]
        if matches:
            view.commands.menu.set(items=matches, selected=0)
            view.show(view.commands, above=view.input)
            return
    view.commands.close()

def run_command(index, name):
    view.input.value = ""
    view.commands.close()
    COMMANDS[name]()

class Commands(Popup):
    menu = Menu(on_select=run_command, border=False)
    modal = False                 # the rest of the screen keeps working
    keep_typing = True            # typing still goes to the text box; arrows and Enter come here
    close_on_outside_click = True

class Console(cmdgui.View):
    layout = """
        heading
        stdout
        input
    """
    heading = Label("Console App!", align="center")
    input = TextInput(placeholder="type and press Enter, / for commands",
                      on_submit=enter_text, on_change=typed)
    commands = Commands()

view = Console(quit_key=None)  # so "q" can be typed anywhere
view.wait()
