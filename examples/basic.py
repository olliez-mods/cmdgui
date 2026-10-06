from cmdgui import CMDGUI_View
import time

view = CMDGUI_View("""
    button[start]{b}  button[pause]{nb} . . . draw_mouse[canvas] - - -
    stdout[out]       -                - - - |                  - - -
    |                 -                - - - |                  - - -
""")

running = True

def start():
    global running
    running = True
    print("started")

def pause():
    global running
    running = False
    print("paused")

view.start.text = "Start"
view.start.on_click(start)
view.pause.text = "Pause"
view.pause.on_click(pause)

view.start.refresh()
view.pause.refresh()

i = 0
while i < 60:
    if running:
        print(f"tick {i}")
        i += 1
    time.sleep(0.5)
