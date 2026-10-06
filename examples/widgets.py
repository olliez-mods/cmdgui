from cmdgui import View, Label, TextInput, Button, Toggle, Menu, Table, ProgressBar, Checkbox
import time

# Tab / Shift+Tab or click to move focus, q to quit (unless typing in the text box)

def greet():
    print(f"Hello, {view.name.value or 'stranger'}! 👋")

class Demo(View):
    layout = """
        heading  -       -
        name     greet   fast
        fruit    scores  -
        |        stdout  -
        bar      -       done
    """
    heading = Label("cmdgui widget demo  ·  Tab to move  ·  q to quit", align="center")
    name = TextInput(placeholder="your name", title="name",
                     on_submit=lambda value: print(f"submitted {value!r}"))
    greet = Button("Greet", on_click=greet)
    fast = Toggle("fast", on_change=lambda on: print("fast mode", "on" if on else "off"))
    fruit = Menu(["apple", "banana", "cherry", "dragonfruit", "elderberry", "fig", "grape"],
                 on_select=lambda i, item: print(f"picked {item}"))
    scores = Table(["name", "score", "city"], rows=[
        ["Ada", 98, "London"], ["Linus", 87, "Helsinki"], ["Grace", 91, "New York"],
        ["Guido", 85, "Haarlem"], ["Margaret", 99, "Boston"],
    ])
    bar = ProgressBar()
    done = Checkbox("done", on_change=lambda checked: print("done:", checked))

view = Demo()
view.on_key("ctrl+r", lambda: print("ctrl+r pressed"))

# The main program keeps running, the view handles itself
progress = 0.0
while view.running:
    progress = (progress + (0.05 if view.fast.checked else 0.01)) % 1.0
    view.bar.value = progress
    time.sleep(0.1)
