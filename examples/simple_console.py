import cmdgui
from cmdgui.widgets import *

def enter_text(text):
    view.input.value = ""
    print(text)

class Console(cmdgui.View):
    layout = """
        heading
        stdout
        input
    """
    heading = Label("Console App!", align="center")
    input = TextInput(placeholder="type and press Enter", on_submit=enter_text)
view = Console()

view.wait()
