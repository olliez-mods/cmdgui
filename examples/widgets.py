from cmdgui import View
import time

# Tab / Shift+Tab or click to move focus, q to quit (unless typing in the text box)
view = View("""
    label[heading]     -                  -
    text_input[name]   button[greet]      toggle[fast]
    menu[fruit]        table[scores]      -
    |                  stdout[log]        -
    progress_bar[bar]  -                  checkbox[done]
""")

view.heading.text = "cmdgui widget demo  ·  Tab to move  ·  q to quit"
view.heading.align = "center"

view.name.placeholder = "your name"
view.name.title = "name"
view.name.on_submit(lambda value: print(f"submitted {value!r}"))
view.greet.text = "Greet"
view.greet.on_click(lambda: print(f"Hello, {view.name.value or 'stranger'}! 👋"))

view.fast.text = "fast"
view.fast.on_change(lambda on: print("fast mode", "on" if on else "off"))
view.done.text = "done"
view.done.on_change(lambda checked: print("done:", checked))

view.fruit.items = ["apple", "banana", "cherry", "dragonfruit", "elderberry", "fig", "grape"]
view.fruit.on_select(lambda i, item: print(f"picked {item}"))

view.scores.columns = ["name", "score", "city"]
view.scores.rows = [["Ada", 98, "London"], ["Linus", 87, "Helsinki"], ["Grace", 91, "New York"],
                    ["Guido", 85, "Haarlem"], ["Margaret", 99, "Boston"]]

view.on_key("ctrl+r", lambda: print("ctrl+r pressed"))

# The main program keeps running, the view handles itself
progress = 0.0
while view.running:
    progress = (progress + (0.05 if view.fast.checked else 0.01)) % 1.0
    view.bar.value = progress
    time.sleep(0.1)
