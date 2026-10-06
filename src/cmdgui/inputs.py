import queue
import re
import sys

from .shorts import ESC, write
from ._platform import Terminal


class Input():
    def __init__(self, type, details):
        self.type:str = type
        self.details:dict = details

    def __repr__(self):
        return f"Input({self.type!r}, {self.details!r})"


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
# Other escape sequences: ESC [ params final, or ESC O final (some terminals' arrow keys)
CSI = re.compile(r"\x1b\[([0-9;]*)([A-Za-z~])")
SS3 = re.compile(r"\x1bO([A-Za-z])")

KEY_NAMES = {
    "A": "up", "B": "down", "C": "right", "D": "left", "H": "home", "F": "end", "Z": "shift_tab",
    "1~": "home", "2~": "insert", "3~": "delete", "4~": "end", "5~": "page_up", "6~": "page_down",
    "7~": "home", "8~": "end",
}
CHAR_NAMES = {"\r": "enter", "\n": "enter", "\t": "tab", "\x7f": "backspace", "\x08": "backspace",
              "\x1b": "escape", " ": "space"}
MODIFIERS = {"2": "shift", "3": "alt", "4": "alt+shift", "5": "ctrl", "6": "ctrl+shift", "7": "ctrl+alt"}

_terminal = Terminal()
_buffer = ""

# Text written to sys.stdout / sys.stderr while intercepted
_text_queue = queue.SimpleQueue()
_stderr_log = [] # everything written to stderr, shown again after the view closes


class StreamInterceptor:
    """Stands in for sys.stdout or sys.stderr and turns everything written
    into "stdout" / "stderr" inputs."""
    def __init__(self, real, kind):
        self.real = real
        self.kind = kind
    def write(self, s):
        if s:
            _text_queue.put((self.kind, s))
            if self.kind == "stderr":
                _stderr_log.append(s)
            _terminal.wake()
        return len(s)
    def flush(self):
        pass
    def __getattr__(self, name):
        # Anything else (encoding, fileno, isatty...) comes from the real stream
        return getattr(self.real, name)


def enable():
    """Raw keyboard mode, mouse reporting, and capture print output."""
    _stderr_log.clear()
    _terminal.enable()
    write(MOUSE_ON)
    sys.stdout = StreamInterceptor(sys.stdout, "stdout")
    sys.stderr = StreamInterceptor(sys.stderr, "stderr")


def disable():
    """Undo enable(). Safe to call more than once."""
    if isinstance(sys.stdout, StreamInterceptor):
        sys.stdout = sys.stdout.real
    if isinstance(sys.stderr, StreamInterceptor):
        sys.stderr = sys.stderr.real
    write(MOUSE_OFF)
    _terminal.disable()


def captured_stderr():
    """Everything written to stderr since enable(), e.g. tracebacks."""
    return "".join(_stderr_log)


def wake():
    """Make read_inputs() return straight away. Safe from any thread."""
    _terminal.wake()


def read_inputs(timeout=0.1):
    """Wait up to timeout seconds for input, and return it as a list of Inputs."""
    global _buffer
    _buffer += _terminal.read(timeout)

    inputs = []

    # print() does several writes per call, so merge queued text into one input per stream
    while not _text_queue.empty():
        kind, text = _text_queue.get()
        if inputs and inputs[-1].type == kind:
            inputs[-1].details["text"] += text
        else:
            inputs.append(Input(kind, {"text": text}))

    while _buffer:
        if _buffer.startswith("\x1b[<"):
            match = SGR_MOUSE.match(_buffer)
            if not match:
                break  # incomplete mouse report, wait for the rest
            inputs.append(_mouse_input(*match.groups()))
            _buffer = _buffer[match.end():]
        elif _buffer.startswith("\x1b[") or _buffer.startswith("\x1bO"):
            match = CSI.match(_buffer) or SS3.match(_buffer)
            if not match:
                if len(_buffer) < 8:
                    break  # incomplete, wait for the rest
                match = re.match(r"\x1b.", _buffer) # garbage, skip it
            inputs.append(_sequence_key(match))
            _buffer = _buffer[match.end():]
        elif _buffer.startswith("\x1b") and len(_buffer) > 1:
            inputs.append(_key("alt+" + _char_name(_buffer[1])))
            _buffer = _buffer[2:]
        else:
            inputs.append(_key(_char_name(_buffer[0]), _buffer[0]))
            _buffer = _buffer[1:]
    return inputs


def _key(name, char=None):
    """A key input. char is the printable character typed, if any."""
    printable = char is not None and (char == " " or char.isprintable())
    return Input("key", {"key": name, "char": char if printable else None})


def _char_name(char):
    if char in CHAR_NAMES:
        return CHAR_NAMES[char]
    if "\x01" <= char <= "\x1a":
        return "ctrl+" + chr(ord(char) + 96)
    return char


def _sequence_key(match):
    groups = match.groups()
    if len(groups) == 1:  # ESC O x
        return _key(KEY_NAMES.get(groups[0], match.group()))
    if len(groups) == 0:  # skipped garbage
        return _key(match.group())
    params, final = groups
    parts = params.split(";") if params else []
    if final == "~":
        name = KEY_NAMES.get((parts[0] if parts else "") + "~", match.group())
    else:
        name = KEY_NAMES.get(final, match.group())
    if len(parts) == 2 and parts[1] in MODIFIERS:  # e.g. ESC [1;5A is ctrl+up
        name = MODIFIERS[parts[1]] + "+" + name
    return _key(name)


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
