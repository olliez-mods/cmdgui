from cmdgui import CMDGUI_View
from cmdgui.widgets import *
import time

view = CMDGUI_View()
view.add(DrawMouse())
view.add(Stdout())
view.add(Button())

for i in range(20):
    print(f"tick {i}")
    time.sleep(0.5)
