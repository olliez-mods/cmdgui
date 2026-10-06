from cmdgui import View, Label, TextInput, TextArea, Button, Toggle, Menu, Table, ProgressBar, Checkbox, Slider, RadioGroup, style
import time

# Tab / Shift+Tab or click to move focus, q to quit (unless typing in the text box)

def greet():
    print(f"Hello, {view.name.value or 'stranger'}! 👋")

class Demo(View):

    def on_radiogroup(i, opt):
        print(opt)
        view.theme["progress"] = style(fg=opt)

    layout = """
        heading  -       -
        name     greet   fast
        fruit    scores  -
        |        stdout  -
        notes    sizeSlider    color
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
    notes = TextArea(placeholder="notes (Enter for a new line)")
    sizeSlider = Slider(5, min=1, max=10, step=1, title="size", border=True,
                  on_change=lambda value: print("size", value))
    color = RadioGroup(["red", "green", "blue"], title="color", border=True,
                       on_change=on_radiogroup)
    
    bar = ProgressBar()
    done = Checkbox("done", on_change=lambda checked: print("done:", checked))

view = Demo()
view.on_key("ctrl+r", lambda: print("ctrl+r pressed"))
view.color.select(1)

# The main program keeps running, the view handles itself
progress = 0.0
while view.running:
    progress = (progress + (0.05 if view.fast.checked else 0.01)) % 1.0
    view.bar.value = progress
    time.sleep(0.1)
