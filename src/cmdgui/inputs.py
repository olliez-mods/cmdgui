import os
import queue
import re
import select
import sys
import termios

from .shorts import ESC, write


class Input():
    def __init__(self, type, details):
        self.type:str = type
        self.details:dict = details


class Mouse():
    """Current mouse state, kept up to date by the view before each input is
    handed to widgets. Coordinates are 0-based screen positions."""
    def __init__(self):
        self.x = 0
        self.y = 0
        self.prev_x = 0 # position before the current input
        self.prev_y = 0
        self.buttons = set() # held buttons: 0 left, 1 middle, 2 right

    def pos(self):
        return self.x, self.y

    def is_down(self, button=0):
        return button in self.buttons

    @property
    def moved(self):
        """True if the current input moved the mouse to a different cell."""
        return (self.x, self.y) != (self.prev_x, self.prev_y)

mouse = Mouse()


def update_state(input):
    """Apply an input to the shared state (mouse position and buttons)."""
    if not input.type.startswith("mouse"):
        return
    mouse.prev_x, mouse.prev_y = mouse.x, mouse.y
    mouse.x, mouse.y = input.details["x"], input.details["y"]
    if input.type == "mouse_down":
        mouse.buttons.add(input.details["button"])
    elif input.type == "mouse_up":
        mouse.buttons.discard(input.details["button"])
    elif input.type == "mouse_move" and "button" not in input.details:
        mouse.buttons.clear() # no button held; fixes a release we missed (e.g. outside the window)

# Mouse tracking: 1003 = report all motion (not just while a button is held),
# 1006 = SGR encoding, which gives readable decimal coordinates with no size limit
MOUSE_ON = ESC + "?1003h" + ESC + "?1006h"
MOUSE_OFF = ESC + "?1003l" + ESC + "?1006l"

# SGR mouse report: ESC [ < button ; x ; y  then M (press/move) or m (release)
SGR_MOUSE = re.compile(r"\x1b\[<(\d+);(\d+);(\d+)([Mm])")

_saved_attrs = None
_buffer = ""

# Text written to sys.stdout while intercepted. Writing a byte to the wake pipe
# makes read_inputs() return immediately instead of waiting out its timeout.
_stdout_queue = queue.SimpleQueue()
_wake_r, _wake_w = os.pipe()
os.set_blocking(_wake_w, False)


class StdoutInterceptor:
    """Stands in for sys.stdout and turns everything written into "stdout" inputs."""
    def __init__(self, real):
        self.real = real
    def write(self, s):
        if s:
            _stdout_queue.put(s)
            try:
                os.write(_wake_w, b"x")
            except BlockingIOError:
                pass  # pipe full, the input thread is already due to wake up
        return len(s)
    def flush(self):
        pass
    def __getattr__(self, name):
        # Anything else (encoding, fileno, isatty...) comes from the real stdout
        return getattr(self.real, name)


def enable():
    """Put the terminal into raw-ish mode and turn on mouse reporting."""
    global _saved_attrs
    fd = sys.stdin.fileno()
    _saved_attrs = termios.tcgetattr(fd)
    attrs = termios.tcgetattr(fd)
    # No line buffering, no echo. ISIG stays on so Ctrl+C still raises KeyboardInterrupt.
    attrs[3] &= ~(termios.ICANON | termios.ECHO)
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    write(MOUSE_ON)
    sys.stdout = StdoutInterceptor(sys.stdout)


def disable():
    """Undo enable(). Safe to call more than once."""
    global _saved_attrs
    if isinstance(sys.stdout, StdoutInterceptor):
        sys.stdout = sys.stdout.real
    write(MOUSE_OFF)
    if _saved_attrs is not None:
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, _saved_attrs)
        _saved_attrs = None


def read_inputs(timeout=0.1):
    """Wait up to timeout seconds for input, and return it as a list of Inputs."""
    global _buffer
    fd = sys.stdin.fileno()
    ready, _, _ = select.select([fd, _wake_r], [], [], timeout)
    if fd in ready:
        _buffer += os.read(fd, 1024).decode(errors="replace")
    if _wake_r in ready:
        os.read(_wake_r, 4096)

    inputs = []

    # print() does several writes per call, so merge everything queued into one input
    text = ""
    while not _stdout_queue.empty():
        text += _stdout_queue.get()
    if text:
        inputs.append(Input("stdout", {"text": text}))

    while _buffer:
        if _buffer.startswith("\x1b["):
            match = SGR_MOUSE.match(_buffer)
            if match:
                inputs.append(_mouse_input(*match.groups()))
                _buffer = _buffer[match.end():]
                continue
            if _buffer.startswith("\x1b[<"):
                break  # incomplete mouse report, wait for the rest
            # Other escape sequences (arrow keys etc.): ESC [ params final-letter
            match = re.match(r"\x1b\[[0-9;]*[A-Za-z~]", _buffer)
            if not match:
                break  # incomplete, wait for the rest
            inputs.append(Input("key", {"key": match.group()}))
            _buffer = _buffer[match.end():]
        else:
            inputs.append(Input("key", {"key": _buffer[0]}))
            _buffer = _buffer[1:]
    return inputs


def _mouse_input(button, x, y, final):
    button, x, y = int(button), int(x) - 1, int(y) - 1  # to 0-based screen coords
    details = {"x": x, "y": y}
    if button & 64:
        details["direction"] = "up" if button & 1 == 0 else "down"
        return Input("mouse_scroll", details)
    if button & 32:
        if button & 3 != 3:
            details["button"] = button & 3
        return Input("mouse_move", details)
    details["button"] = button & 3  # 0 left, 1 middle, 2 right
    return Input("mouse_down" if final == "M" else "mouse_up", details)
