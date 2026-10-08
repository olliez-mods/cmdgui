"""A small terminal emulator, for the Terminal widget: feed it what a program writes, and
it keeps the screen that would show, as rows of characters and styles like a Canvas.

It covers what shells and most full-screen programs use: cursor movement, erasing,
scroll regions, inserting and deleting, colours (16, 256 and true colour), the
alternative screen (vim, less, top), wide characters, line drawing, and answering
"where's the cursor?" Mouse reporting to the program isn't supported."""
import re
from .shorts import ESC, char_width

# Runs of plain text, handled in one go
PLAIN = re.compile(r"[^\x00-\x1f\x7f\x1b]+")
# The DEC line drawing set (ESC ( 0), used by some programs for boxes
LINE_DRAWING = dict(zip("`afgjklmnopqrstuvwxyz{|}~",
                        "◆▒°±┘┐┌└┼⎺⎻─⎼⎽├┤┴┬│≤≥π≠£·"))
DEFAULT = (False, False, False, False, False, None, None) # bold, dim, italic, underline, reverse, fg, bg


class Screen:
    def __init__(self, width, height, scrollback=1000):
        self.width, self.height = max(1, width), max(1, height)
        self.scrollback = scrollback
        self.history = [] # (chars, styles) rows scrolled off the top of the main screen
        self.chars = [self._blank_chars() for _ in range(self.height)]
        self.styles = [self._blank_styles("") for _ in range(self.height)]
        self.replies = [] # what to send back to the program, like a cursor position report
        self.title = None # set by the program (OSC 0 or 2)
        self.cursor_visible = True
        self.app_cursor = False      # arrow keys send ESC O A rather than ESC [ A
        self.bracketed_paste = False
        self._alt = None # the main screen's rows and cursor, while the alternative one is up
        self._state = "ground"
        self._seq = ""   # the escape sequence being read
        self._reset_modes()

    def _reset_modes(self):
        self.x = self.y = 0
        self.attrs = DEFAULT
        self.style = ""
        self.top, self.bottom = 0, self.height - 1 # scroll region
        self.autowrap = True
        self.insert = False
        self.graphics = False # G0 is the line drawing set
        self._wrap_next = False # at the last column: the next character goes on a new line
        self._saved = (0, 0, DEFAULT, False)
        self._styles = {DEFAULT: ""}

    def _blank_chars(self):
        return [" "] * self.width

    def _blank_styles(self, style):
        return [style] * self.width

    @property
    def on_alt_screen(self):
        return self._alt is not None

    # --- Feeding it output ---

    def feed(self, text):
        i, n = 0, len(text)
        while i < n:
            state = self._state
            if state == "ground":
                match = PLAIN.match(text, i)
                if match:
                    for char in match.group(): self._print(char)
                    i = match.end()
                    continue
                self._control(text[i])
            elif state == "escape":
                self._escape(text[i])
            elif state == "charset":
                if self._seq == "(": self.graphics = text[i] == "0"
                self._state = "ground"
            elif state == "csi":
                char = text[i]
                if "\x40" <= char <= "\x7e":
                    self._state = "ground"
                    self._csi(self._seq, char)
                elif char == "\x1b":
                    self._state = "escape" # cancelled
                elif char in "\x18\x1a":
                    self._state = "ground"
                elif char < " ":
                    self._control(char) # controls still work in the middle of a sequence
                else:
                    self._seq += char
            elif state in ("osc", "string"):
                char = text[i]
                if char == "\x07" or (char == "\\" and self._seq.endswith("\x1b")):
                    if state == "osc": self._osc(self._seq.rstrip("\x1b"))
                    self._state = "ground"
                else:
                    self._seq += char
            i += 1

    def _control(self, char):
        if char == "\x1b":
            self._state, self._seq = "escape", ""
        elif char == "\r":
            self.x, self._wrap_next = 0, False
        elif char in "\n\x0b\x0c":
            self._index()
        elif char == "\b":
            self.x, self._wrap_next = max(0, self.x - 1), False
        elif char == "\t":
            self.x = min(self.width - 1, (self.x // 8 + 1) * 8)
        elif char == "\x0e": # shift out / in: G1 / G0, both plain here
            pass

    def _escape(self, char):
        self._state = "ground"
        if char == "[": self._state, self._seq = "csi", ""
        elif char == "]": self._state, self._seq = "osc", ""
        elif char in "PX^_": self._state, self._seq = "string", ""
        elif char in "()*+": self._state, self._seq = "charset", char
        elif char == "#": self._state, self._seq = "charset", char # DECALN and the like: skip one
        elif char == "7": self._save()
        elif char == "8": self._restore()
        elif char == "D": self._index()
        elif char == "E": self.x = 0; self._index()
        elif char == "M": self._reverse_index()
        elif char == "c": self.reset()

    def _osc(self, text):
        number, _, value = text.partition(";")
        if number in ("0", "2"): self.title = value

    # --- Characters ---

    def _print(self, char):
        if self.graphics: char = LINE_DRAWING.get(char, char)
        width = char_width(char)
        if width == 0: # a combining mark: onto the character before
            x = self.x - (0 if self._wrap_next else 1)
            if x >= 0 and self.chars[self.y][x]: self.chars[self.y][x] += char
            return
        if self._wrap_next:
            self.x, self._wrap_next = 0, False
            self._index()
        if width == 2 and self.x == self.width - 1: # no room for both halves here
            if self.autowrap:
                self._put(" ")
                self.x = 0
                self._index()
            else:
                return
        if self.insert: self._insert_chars(width)
        self._put(char)
        if width == 2:
            self.chars[self.y][self.x + 1], self.styles[self.y][self.x + 1] = "", self.style
        if self.x + width >= self.width:
            self.x = self.width - 1
            self._wrap_next = self.autowrap
        else:
            self.x += width

    def _put(self, char):
        """Write one cell at the cursor, blanking the other half of a wide character it cuts."""
        chars, x = self.chars[self.y], self.x
        if chars[x] == "" and x > 0: chars[x - 1] = " "
        if x + 1 < self.width and chars[x + 1] == "": chars[x + 1] = " "
        chars[x], self.styles[self.y][x] = char, self.style

    # --- Moving and scrolling ---

    def _index(self):
        """Down a line, scrolling the region at its bottom."""
        if self.y == self.bottom: self._scroll_up(1)
        elif self.y < self.height - 1: self.y += 1

    def _reverse_index(self):
        if self.y == self.top: self._scroll_down(1)
        elif self.y > 0: self.y -= 1

    def _scroll_up(self, count, keep=True):
        """Scroll the region up. keep: rows leaving the top of the main screen go into the
        scrollback (not for deleted lines)."""
        top, bottom = self.top, self.bottom
        count = min(count, bottom - top + 1)
        for _ in range(count):
            chars, styles = self.chars.pop(top), self.styles.pop(top)
            if keep and top == 0 and self._alt is None and self.scrollback:
                self.history.append((chars, styles))
                if len(self.history) > self.scrollback: del self.history[0]
            self.chars.insert(bottom, self._blank_chars())
            self.styles.insert(bottom, self._blank_styles(self._erase_style()))

    def _scroll_down(self, count):
        top, bottom = self.top, self.bottom
        for _ in range(min(count, bottom - top + 1)):
            del self.chars[bottom], self.styles[bottom]
            self.chars.insert(top, self._blank_chars())
            self.styles.insert(top, self._blank_styles(self._erase_style()))

    def _move(self, x=None, y=None):
        if x is not None: self.x = max(0, min(self.width - 1, x))
        if y is not None: self.y = max(0, min(self.height - 1, y))
        self._wrap_next = False

    def _save(self):
        self._saved = (self.x, self.y, self.attrs, self.graphics)

    def _restore(self):
        x, y, attrs, self.graphics = self._saved
        self._move(x, y)
        self._set_attrs(attrs)

    # --- Erasing ---

    def _erase_style(self):
        """Erased cells keep the background colour (but nothing else)."""
        bg = self.attrs[6]
        return f"{ESC}{bg}m" if bg else ""

    def _erase(self, y, start, end):
        style = self._erase_style()
        chars, styles = self.chars[y], self.styles[y]
        if 0 < start < self.width and chars[start] == "": chars[start - 1] = " "
        if end < self.width and chars[end] == "": chars[end] = " "
        for x in range(max(0, start), min(self.width, end)):
            chars[x], styles[x] = " ", style

    def _insert_chars(self, count):
        chars, styles, x = self.chars[self.y], self.styles[self.y], self.x
        count = min(count, self.width - x)
        chars[x:x] = [" "] * count
        styles[x:x] = [self._erase_style()] * count
        del chars[self.width:], styles[self.width:]

    def _delete_chars(self, count):
        chars, styles, x = self.chars[self.y], self.styles[self.y], self.x
        count = min(count, self.width - x)
        del chars[x:x + count], styles[x:x + count]
        chars.extend([" "] * count)
        styles.extend([self._erase_style()] * count)

    # --- CSI sequences: ESC [ ... ---

    def _csi(self, seq, final):
        private = seq[:1] if seq[:1] in "?>=<" else ""
        body = seq[len(private):].rstrip(" !\"#$%&'()*+,-./")
        intermediate = seq[len(private) + len(body):]
        if final == "m" and not private:
            self._sgr(body)
            return
        params = [int(p) if p.isdigit() else 0 for p in re.split(r"[;:]", body)] if body else []
        def arg(i=0, default=1):
            return params[i] if len(params) > i and params[i] else default
        if intermediate: return # cursor shape (q) and the like
        if private:
            if final in "hl": self._modes(params, final == "h", private)
            elif final == "c" and private == ">": self.replies.append("\x1b[>0;0;0c")
            return
        if final == "A": self._move(y=max(self.top if self.y >= self.top else 0, self.y - arg()))
        elif final in "Be": self._move(y=min(self.bottom if self.y <= self.bottom else self.height - 1, self.y + arg()))
        elif final in "Ca": self._move(x=self.x + arg())
        elif final == "D": self._move(x=self.x - arg())
        elif final == "E": self._move(0, self.y + arg())
        elif final == "F": self._move(0, self.y - arg())
        elif final in "G`": self._move(x=arg() - 1)
        elif final in "Hf": self._move(arg(1) - 1, arg(0) - 1)
        elif final == "d": self._move(y=arg() - 1)
        elif final == "J":
            mode = arg(0, 0)
            if mode == 0:
                self._erase(self.y, self.x, self.width)
                for y in range(self.y + 1, self.height): self._erase(y, 0, self.width)
            elif mode == 1:
                self._erase(self.y, 0, self.x + 1)
                for y in range(self.y): self._erase(y, 0, self.width)
            else:
                for y in range(self.height): self._erase(y, 0, self.width)
                if mode == 3: self.history.clear()
        elif final == "K":
            mode = arg(0, 0)
            start, end = {0: (self.x, self.width), 1: (0, self.x + 1)}.get(mode, (0, self.width))
            self._erase(self.y, start, end)
        elif final in "LM":
            if self.top <= self.y <= self.bottom:
                top, self.top = self.top, self.y
                if final == "L": self._scroll_down(arg())
                else: self._scroll_up(arg(), keep=False)
                self.top = top
                self.x = 0
        elif final == "@": self._insert_chars(arg())
        elif final == "P": self._delete_chars(arg())
        elif final == "X": self._erase(self.y, self.x, self.x + arg())
        elif final == "S": self._scroll_up(arg())
        elif final == "T": self._scroll_down(arg())
        elif final == "r":
            top, bottom = arg(0) - 1, arg(1, self.height) - 1
            if 0 <= top < bottom < self.height:
                self.top, self.bottom = top, bottom
                self._move(0, 0)
        elif final == "s": self._save()
        elif final == "u": self._restore()
        elif final in "hl":
            if 4 in params: self.insert = final == "h"
        elif final == "n":
            if arg() == 6: self.replies.append(f"\x1b[{self.y + 1};{self.x + 1}R")
            elif arg() == 5: self.replies.append("\x1b[0n")
        elif final == "c": self.replies.append("\x1b[?1;2c") # a VT100 with extras
        elif final == "Z": self._move(x=(self.x - 1) // 8 * 8)

    def _modes(self, params, on, private):
        for mode in params:
            if mode == 1: self.app_cursor = on
            elif mode == 7: self.autowrap = on
            elif mode == 25: self.cursor_visible = on
            elif mode == 2004: self.bracketed_paste = on
            elif mode in (47, 1047, 1049): self._switch_screen(on, save_cursor=mode == 1049)

    def _switch_screen(self, alt, save_cursor):
        if alt == (self._alt is not None): return
        if alt:
            if save_cursor: self._save()
            self._alt = (self.chars, self.styles)
            self.chars = [self._blank_chars() for _ in range(self.height)]
            self.styles = [self._blank_styles("") for _ in range(self.height)]
        else:
            self.chars, self.styles = self._alt
            self._alt = None
            if save_cursor: self._restore()
        self.top, self.bottom = 0, self.height - 1

    # --- Colours and styles (SGR) ---

    def _sgr(self, body):
        bold, dim, italic, underline, reverse, fg, bg = self.attrs
        parts = body.split(";") if body else ["0"]
        i = 0
        while i < len(parts):
            part = parts[i]
            if ":" in part: # 38:2::r:g:b, 4:3 (curly underline) and so on
                sub = [p for p in part.split(":")]
                code = int(sub[0] or 0)
                if code in (38, 48):
                    nums = [int(p or 0) for p in sub[1:]]
                    colour = None
                    if nums[:1] == [5] and len(nums) >= 2: colour = f"{code};5;{nums[1]}"
                    elif nums[:1] == [2] and len(nums) >= 4: colour = f"{code};2;" + ";".join(map(str, nums[-3:]))
                    if code == 38: fg = colour
                    else: bg = colour
                elif code == 4:
                    underline = sub[1:2] != ["0"]
                i += 1
                continue
            code = int(part) if part.isdigit() else 0
            if code == 0: bold, dim, italic, underline, reverse, fg, bg = DEFAULT
            elif code == 1: bold = True
            elif code == 2: dim = True
            elif code == 3: italic = True
            elif code == 4: underline = True
            elif code == 7: reverse = True
            elif code == 22: bold = dim = False
            elif code == 23: italic = False
            elif code == 24: underline = False
            elif code == 27: reverse = False
            elif 30 <= code <= 37 or 90 <= code <= 97: fg = str(code)
            elif code == 39: fg = None
            elif 40 <= code <= 47 or 100 <= code <= 107: bg = str(code)
            elif code == 49: bg = None
            elif code in (38, 48):
                kind = parts[i + 1] if i + 1 < len(parts) else ""
                colour = None
                if kind == "5" and i + 2 < len(parts):
                    colour, i = f"{code};5;{parts[i + 2] or 0}", i + 2
                elif kind == "2" and i + 4 < len(parts):
                    colour, i = f"{code};2;{parts[i + 2] or 0};{parts[i + 3] or 0};{parts[i + 4] or 0}", i + 4
                if code == 38: fg = colour
                else: bg = colour
            i += 1
        self._set_attrs((bold, dim, italic, underline, reverse, fg, bg))

    def _set_attrs(self, attrs):
        self.attrs = attrs
        style = self._styles.get(attrs)
        if style is None:
            bold, dim, italic, underline, reverse, fg, bg = attrs
            codes = [code for on, code in ((bold, "1"), (dim, "2"), (italic, "3"), (underline, "4"),
                                           (reverse, "7")) if on] + [c for c in (fg, bg) if c]
            style = self._styles[attrs] = f"{ESC}{';'.join(codes)}m" if codes else ""
        self.style = style

    # --- Size ---

    def resize(self, width, height):
        width, height = max(1, width), max(1, height)
        if (width, height) == (self.width, self.height): return
        screens = [(self.chars, self.styles)] + ([self._alt] if self._alt else []) # shown first, main last
        for n, (chars, styles) in enumerate(screens):
            extra = len(chars) - height
            if extra > 0:
                # Fewer rows: from the top as far as keeps the cursor on screen (into the
                # scrollback, for the main screen), the rest from the bottom
                from_top = max(0, min(extra, self.y - (height - 1))) if n == 0 else 0
                for _ in range(from_top):
                    row = (chars.pop(0), styles.pop(0))
                    if n == len(screens) - 1 and self.scrollback: self.history.append(row)
                if n == 0: self.y -= from_top
                del chars[height:], styles[height:]
            while len(chars) < height:
                chars.append([" "] * width)
                styles.append([""] * width)
            for c, st in zip(chars, styles):
                if len(c) > width:
                    del c[width:], st[width:]
                    if char_width(c[-1] or " ") == 2: c[-1] = " " # its second half is cut off
                else:
                    c.extend([" "] * (width - len(c)))
                    st.extend([""] * (width - len(st)))
        if self.scrollback: del self.history[:-self.scrollback]
        self.width, self.height = width, height
        self.top, self.bottom = 0, height - 1
        self._move(self.x, self.y)

    def reset(self):
        """ESC c: back to how it started (the scrollback stays)."""
        if self._alt: self._switch_screen(False, save_cursor=False)
        self.chars = [self._blank_chars() for _ in range(self.height)]
        self.styles = [self._blank_styles("") for _ in range(self.height)]
        self.cursor_visible, self.app_cursor, self.bracketed_paste = True, False, False
        self._reset_modes()

    def rows(self, scroll=0):
        """The rows to show: the screen, or scroll rows back into the scrollback."""
        if not scroll or self._alt: return list(zip(self.chars, self.styles))
        scroll = min(scroll, len(self.history))
        rows = self.history[len(self.history) - scroll:] + list(zip(self.chars, self.styles))
        return rows[:self.height]
