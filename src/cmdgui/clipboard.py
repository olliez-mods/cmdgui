"""Copying to the system clipboard. A terminal app can't reach the clipboard
directly, so copy() tries both ways there are:

- OSC 52, an escape code asking the terminal to copy. Works over SSH. Most modern
  terminals support it (kitty, WezTerm, Ghostty, Alacritty, Windows Terminal, foot,
  iTerm2 once allowed in its settings); macOS's Terminal.app doesn't.
- the system's own tool (pbcopy, wl-copy, xclip, xsel, clip), when running locally.

Pasting from the system clipboard is done by the terminal (Cmd+V, or Ctrl+Shift+V),
which sends the text to the app as a paste. paste() gives what was last copied in
this program, for Ctrl+V."""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
from .shorts import write

_last = "" # the last text copied, for paste()

# Clipboard tools, most likely first: (command, needs)
TOOLS = [
    (["pbcopy"], "darwin"),
    (["wl-copy"], "WAYLAND_DISPLAY"),
    (["xclip", "-selection", "clipboard"], "DISPLAY"),
    (["xsel", "--clipboard", "--input"], "DISPLAY"),
    (["clip"], "win32"),
]


def copy(text: str) -> None:
    """Put text on the system clipboard (as far as the terminal allows), and keep it
    for paste()."""
    global _last
    _last = text
    write("\x1b]52;c;" + base64.b64encode(text.encode("utf-8")).decode("ascii") + "\x07")
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        return # the tools would copy on the remote machine, not yours
    for command, needs in TOOLS:
        if (needs == sys.platform or os.environ.get(needs)) and shutil.which(command[0]):
            try:
                subprocess.run(command, input=text.encode("utf-8"), timeout=2, check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except (OSError, subprocess.SubprocessError):
                continue
            return


def paste() -> str:
    """The text last copied with copy() in this program."""
    return _last
