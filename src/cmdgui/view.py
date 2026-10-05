import atexit
import sys
import threading
from .shorts import *
from .widgets import *
from . import inputs

# Setup terminal
def setup():
    write(ESC + "?1049h" + hide_cursor()) # alternative screen
    inputs.enable()

def teardown():
    inputs.disable()
    write(show_cursor() + ESC + "?1049l") # back to the normal screen

class CMDGUI_View():
    def __init__(self, layout:str = None):
        self.widgets = []
        self.lock = threading.Lock()
        self.running = True
        setup()
        atexit.register(self.stop)
        self.thread = threading.Thread(target=self._input_loop, daemon=True)
        self.thread.start()

    def add(self, widget):
        with self.lock:
            self.widgets.append(widget)
            widget.super_draw()
        return widget

    def draw(self):
        with self.lock:
            for widget in self.widgets:
                widget.super_draw()

    def stop(self):
        if self.running:
            self.running = False
            self.thread.join()
            teardown()

    def _input_loop(self):
        while self.running:
            for input in inputs.read_inputs(timeout=0.05):
                with self.lock:
                    inputs.update_state(input)
                    for widget in self.widgets:
                        widget.super_on_input(input)
