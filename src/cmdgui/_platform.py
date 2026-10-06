"""The OS-specific bits: raw keyboard mode, reading input with a timeout, and
waking a blocked read from another thread. Everything else is shared."""
import codecs
import os
import sys

WINDOWS = os.name == "nt"


if not WINDOWS:
    import select
    import termios

    class Terminal:
        def __init__(self):
            self._saved = None
            self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            self._wake_r, self._wake_w = os.pipe()
            os.set_blocking(self._wake_w, False)

        def enable(self):
            fd = sys.stdin.fileno()
            self._saved = termios.tcgetattr(fd)
            attrs = termios.tcgetattr(fd)
            # No line buffering or echo. Ctrl+C, Ctrl+V, Ctrl+S and so on come through as keys
            # (ISIG, IEXTEN, IXON off): the view turns Ctrl+C back into KeyboardInterrupt when
            # it isn't copying, and Ctrl+S no longer freezes the output
            attrs[3] &= ~(termios.ICANON | termios.ECHO | termios.ISIG | termios.IEXTEN)
            attrs[0] &= ~termios.IXON
            termios.tcsetattr(fd, termios.TCSANOW, attrs)

        def disable(self):
            if self._saved is not None:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, self._saved)
                self._saved = None

        def read(self, timeout):
            """Wait up to timeout seconds, return whatever was typed ("" if nothing)."""
            fd = sys.stdin.fileno()
            ready, _, _ = select.select([fd, self._wake_r], [], [], timeout)
            text = ""
            if fd in ready:
                text = self._decoder.decode(os.read(fd, 1024))  # handles characters split across reads
            if self._wake_r in ready:
                os.read(self._wake_r, 4096)
            return text

        def wake(self):
            """Make a read() that's waiting return straight away. Safe from any thread."""
            try:
                os.write(self._wake_w, b"x")
            except BlockingIOError:
                pass  # pipe full, it's already going to wake up


else:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    STD_INPUT_HANDLE, STD_OUTPUT_HANDLE = -10, -11
    ENABLE_PROCESSED_INPUT = 0x0001
    ENABLE_LINE_INPUT = 0x0002
    ENABLE_ECHO_INPUT = 0x0004
    ENABLE_QUICK_EDIT_MODE = 0x0040
    ENABLE_EXTENDED_FLAGS = 0x0080
    ENABLE_VIRTUAL_TERMINAL_INPUT = 0x0200
    ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
    KEY_EVENT = 0x0001
    WAIT_TIMEOUT = 0x102

    class KEY_EVENT_RECORD(ctypes.Structure):
        _fields_ = [("bKeyDown", wintypes.BOOL), ("wRepeatCount", wintypes.WORD),
                    ("wVirtualKeyCode", wintypes.WORD), ("wVirtualScanCode", wintypes.WORD),
                    ("UnicodeChar", wintypes.WCHAR), ("dwControlKeyState", wintypes.DWORD)]

    class _EVENT(ctypes.Union):
        # KEY_EVENT_RECORD is the largest member we read; pad to the real union size (16 bytes)
        _fields_ = [("KeyEvent", KEY_EVENT_RECORD), ("_pad", ctypes.c_byte * 16)]

    class INPUT_RECORD(ctypes.Structure):
        _fields_ = [("EventType", wintypes.WORD), ("Event", _EVENT)]

    class Terminal:
        """Windows console. With virtual terminal input on, keys and the mouse
        arrive as the same escape sequences Unix terminals send."""
        def __init__(self):
            self._in = kernel32.GetStdHandle(STD_INPUT_HANDLE)
            self._out = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
            self._saved = None
            self._wake_event = kernel32.CreateEventW(None, False, False, None)

        def enable(self):
            in_mode, out_mode = wintypes.DWORD(), wintypes.DWORD()
            kernel32.GetConsoleMode(self._in, ctypes.byref(in_mode))
            kernel32.GetConsoleMode(self._out, ctypes.byref(out_mode))
            self._saved = (in_mode.value, out_mode.value)
            new_in = (in_mode.value | ENABLE_VIRTUAL_TERMINAL_INPUT | ENABLE_EXTENDED_FLAGS | ENABLE_PROCESSED_INPUT) \
                & ~(ENABLE_LINE_INPUT | ENABLE_ECHO_INPUT | ENABLE_QUICK_EDIT_MODE)
            kernel32.SetConsoleMode(self._in, new_in)
            kernel32.SetConsoleMode(self._out, out_mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)

        def disable(self):
            if self._saved is not None:
                kernel32.SetConsoleMode(self._in, self._saved[0])
                kernel32.SetConsoleMode(self._out, self._saved[1])
                self._saved = None

        def read(self, timeout):
            handles = (wintypes.HANDLE * 2)(self._in, self._wake_event)
            result = kernel32.WaitForMultipleObjects(2, handles, False, int(timeout * 1000))
            if result != 0:  # timed out, or woken
                return ""
            text = []
            count = wintypes.DWORD()
            kernel32.GetNumberOfConsoleInputEvents(self._in, ctypes.byref(count))
            if count.value:
                records = (INPUT_RECORD * count.value)()
                read = wintypes.DWORD()
                kernel32.ReadConsoleInputW(self._in, records, count.value, ctypes.byref(read))
                for record in records[:read.value]:
                    key = record.Event.KeyEvent
                    if record.EventType == KEY_EVENT and key.bKeyDown and key.UnicodeChar != "\0":
                        text.append(key.UnicodeChar * max(1, key.wRepeatCount))
            return "".join(text)

        def wake(self):
            kernel32.SetEvent(self._wake_event)
