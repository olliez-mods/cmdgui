from __future__ import annotations

import codecs
import os
import shlex
import signal
import sys
import threading
from typing import Any, Callable, Optional, Union
from ..shorts import *
from ..vt import Screen
from .base import Widget, field, _call

# Arrow keys and Home/End as the program asks for them: ESC O A in its "application" mode
APP_CURSOR = {f"\x1b[{c}": f"\x1bO{c}" for c in "ABCDHF"}


class Terminal(Widget):
    """Runs a program in a terminal of its own, inside the layout: a shell, a REPL, or
    anything full-screen like top or vim.

        shell = Terminal()                         # your shell ($SHELL)
        repl = Terminal([sys.executable, "-q"])    # a list runs the program directly
        build = Terminal("make 2>&1 | less")       # a string runs through the shell

    It starts when it's first laid out. While it's focused every key goes to the program,
    Tab and Ctrl+C included; release_key (Ctrl+] by default) moves focus on, or click
    another widget. Scroll back with the mouse wheel. terminal.run("ls") types a command
    and Enter, write() sends anything, and on_exit(fn(code)) is told when the program ends.
    macOS and Linux only."""
    command: Union[str, list, None] = field(default=None, kw_only=False)
    cwd: Optional[str] = None
    env: Optional[dict] = None    # added to (or replacing) your environment's variables
    scrollback: int = 1000        # lines kept above the screen
    release_key: str = "ctrl+]"   # leaves the terminal, since every other key goes to the program
    exit_callback: Optional[Callable[[int], Any]] = field(default=None, alias="on_exit")
    border = True

    focusable = True
    captures_text = True

    def init(self):
        self._screen: Optional[Screen] = None
        self._process = None
        self._fd: Optional[int] = None
        self._scroll = 0 # rows scrolled back into the history
        self.exit_code: Optional[int] = None # once the program has ended

    def on_exit(self, callback: Callable[[int], Any]): # called with the exit code when the program ends
        self.exit_callback = callback

    def copy(self):
        new = super().copy()
        new.init() # a copy hasn't started yet
        return new

    @property
    def running(self) -> bool:
        return self._process is not None and self.exit_code is None

    @property
    def program_title(self) -> Optional[str]:
        """The title the program set for its window, if it set one."""
        return self._screen.title if self._screen else None

    # --- The program ---

    def start(self) -> None:
        """Start the program, if it isn't running. It starts by itself when first laid
        out; this is for starting it again after it ended."""
        if self.running: return
        try:
            import pty, termios, fcntl, subprocess
        except ImportError:
            raise RuntimeError("Terminal needs macOS or Linux") from None
        width, height = max(1, self.width), max(1, self.height)
        if self._screen is None: self._screen = Screen(width, height, self.scrollback)
        else: self._screen.reset()
        master, slave = pty.openpty()
        self._set_size(master, width, height)
        command = self.command
        shell = os.environ.get("SHELL") or "/bin/sh"
        argv = [shell] if command is None else [shell, "-c", command] if isinstance(command, str) else list(command)
        env = {**os.environ, "TERM": "xterm-256color", "COLORTERM": "truecolor", **(self.env or {})}
        for name in ("COLUMNS", "LINES"): env.pop(name, None) # it asks the terminal instead
        def take_terminal(): # in the new process: make the terminal its controlling one, for job control
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)
        try:
            self._process = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave, cwd=self.cwd, env=env,
                                             start_new_session=True, preexec_fn=take_terminal, close_fds=True)
        except BaseException:
            os.close(master)
            raise
        finally:
            os.close(slave)
        self._fd, self.exit_code, self._scroll = master, None, 0
        threading.Thread(target=self._read, args=(master, self._process), daemon=True).start()
        self.refresh()

    def _read(self, fd, process):
        """Feed the program's output to the screen, until it ends."""
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        while True:
            try:
                data = os.read(fd, 65536)
            except OSError:
                data = b""
            with self._lock():
                if data:
                    self._screen.feed(decoder.decode(data))
                    replies, self._screen.replies = self._screen.replies, []
                    for reply in replies: self._send(reply.encode())
                else:
                    break
            self.refresh()
        code = process.wait()
        if code < 0: code = 128 - code # killed by a signal, as a shell reports it
        try: os.close(fd)
        except OSError: pass
        with self._lock():
            if self._process is not process: return # restarted meanwhile: that one's told instead
            self.exit_code, self._fd = code, None
            self._screen.feed(f"\r\n\x1b[0;2m[exited with code {code}]\x1b[0m")
        self.refresh()
        if self.view: self.view.after(0, lambda: _call(self.exit_callback, code)) # on the view's thread
        else: _call(self.exit_callback, code)

    def _lock(self):
        return self.view.lock if self.view else threading.RLock()

    def write(self, data: Union[str, bytes]) -> None:
        """Send text (or bytes) to the program, as if typed."""
        self._send(data.encode() if isinstance(data, str) else data)

    def run(self, command: str) -> None:
        """Type a command and press Enter: terminal.run("ls -la")."""
        self.write(command + "\r")

    def _send(self, data):
        if self._fd is None or not data: return
        try:
            os.write(self._fd, data)
        except OSError:
            pass

    def kill(self, sig: int = signal.SIGTERM) -> None:
        """Stop the program (on_exit is still called)."""
        if self.running:
            try: os.killpg(self._process.pid, sig) # it and anything it started
            except OSError: pass

    def restart(self) -> None:
        """Stop the program if it's running, and start it again."""
        process = self._process
        if self.running:
            self.kill(signal.SIGKILL)
            process.wait()
        self._process = None
        self.start()

    @staticmethod
    def _set_size(fd, width, height):
        import fcntl, struct, termios
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", height, width, 0, 0))

    # --- Widget ---

    def on_resize(self):
        if self.width <= 0 or self.height <= 0: return
        if self._process is None and self.view is not None:
            self.start() # first laid out: now it knows its size
        elif self._screen is not None:
            with self._lock():
                self._screen.resize(self.width, self.height)
                if self._fd is not None: self._set_size(self._fd, self.width, self.height) # the program gets SIGWINCH

    def _claims_key(self, key):
        return key != self.release_key # everything else is for the program, Ctrl+C and Tab too

    def key_hints(self):
        return [(self.release_key, "Leave")]

    def on_input(self, input):
        screen = self._screen
        if input.type == "key":
            if input.details["key"] == self.release_key:
                if self.view: self.view.focus_next()
                return
            raw = input.details.get("raw") or input.details.get("char") or ""
            if screen is not None and screen.app_cursor: raw = APP_CURSOR.get(raw, raw)
            self._scroll_to(0)
            self.write(raw)
        elif input.type == "paste":
            text = input.details["text"].replace("\n", "\r")
            if screen is not None and screen.bracketed_paste: text = f"\x1b[200~{text}\x1b[201~"
            self._scroll_to(0)
            self.write(text)
        elif input.type == "mouse_scroll" and self.mouse_over() and screen is not None:
            up = input.details["direction"] == "up"
            if screen.on_alt_screen: # less, vim and the like: arrow keys, as other terminals do
                self.write(("\x1bOA" if screen.app_cursor else "\x1b[A") * 3 if up else
                           ("\x1bOB" if screen.app_cursor else "\x1b[B") * 3)
            else:
                self._scroll_to(self._scroll + (3 if up else -3))

    def _scroll_to(self, scroll):
        history = len(self._screen.history) if self._screen else 0
        scroll = max(0, min(history, scroll))
        if scroll != self._scroll:
            self._scroll = scroll
            self.refresh()

    def draw(self, c):
        screen = self._screen
        if screen is None:
            c.text(0, 0, "starting…", self.theme("dim"))
            return
        with self._lock():
            rows = screen.rows(self._scroll)
            for y, (chars, styles) in enumerate(rows[:c.height]):
                if len(chars) == c.width:
                    c.chars[y], c.styles[y] = list(chars), list(styles)
                else:
                    for x, char in enumerate(chars[:c.width]):
                        if char: c.put(x, y, char, styles[x])
            if self._scroll:
                c.text(max(0, c.width - 12), 0, fit(f" ↑ {self._scroll} lines ", c.width), self.theme("selected"))
            elif self.focused and screen.cursor_visible and self.running and \
                    0 <= screen.y < c.height and 0 <= screen.x < c.width:
                c.styles[screen.y][screen.x] = self.theme("cursor")
