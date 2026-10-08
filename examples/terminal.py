import sys
from cmdgui import View, Terminal, Button, KeyHints

# Programs running inside the layout: your shell on the left, a Python REPL on the right.
# Click one (or Tab to it) and type; every key goes to it, Ctrl+C and Tab too, until you
# press Ctrl+] to move on. Try top, vim or less in the shell. Scroll back with the wheel.
# Drag the line between them. The buttons type into the shell; q quits when neither is focused.

def exited(name, code):
    view.notify(f"{name} exited with code {code}. Restart it with the button.", "warning", seconds=5)

class App(View):
    layout = """
        shell{+b}  python{+b}  -
        ls         restart     .
        hints      -           -
    """
    shell = Terminal(title="shell", on_exit=lambda code: exited("The shell", code))
    python = Terminal([sys.executable, "-q"], title="python", on_exit=lambda code: exited("Python", code))
    ls = Button("Run ls -la in the shell", on_click=lambda: view.shell.run("ls -la"))
    restart = Button("Restart python", on_click=lambda: view.python.restart())
    hints = KeyHints()

view = App()
view.adjustable(view.shell, view.python, position=0.6)
view.focus(view.shell)
view.wait()
