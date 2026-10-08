"""Markdown, drawn as styled rows of text: what Text(markdown=True) shows.

render(source, width, theme) gives a list of Rows. It covers the Markdown people write
day to day: headings, paragraphs, bold, italic, `code`, ~~strikethrough~~, links,
lists (bullets, numbers, [ ] tasks, nested), > quotes, code blocks, horizontal rules
and tables. HTML and footnotes are left as text."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from .shorts import ESC, fit, pad_right, text_width, wrap_spans

BOLD, ITALIC, STRIKE = f"{ESC}1m", f"{ESC}3m", f"{ESC}9m"
# The theme keys it uses (see DEFAULT_THEME)
THEME_KEYS = ("md_heading1", "md_heading2", "md_heading", "md_code", "md_code_block", "md_quote",
              "md_quote_text", "md_link", "md_bullet", "md_rule", "md_table_header")
BULLETS = "•◦▪" # by how deep the list is
ENTITIES = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'", "&nbsp;": " "}

FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})\s*([^`\s]*)")
HEADING = re.compile(r"^ {0,3}(#{1,6})(?:\s+(.*?))?(?:\s+#+)?\s*$")
RULE = re.compile(r"^ {0,3}([-*_])(?:\s*\1){2,}\s*$")
QUOTE = re.compile(r"^ {0,3}> ?")
ITEM = re.compile(r"^( {0,3})([-*+]|\d{1,9}[.)])(\s+|$)")
TASK = re.compile(r"^\[([ xX])\]\s+")
SETEXT = re.compile(r"^ {0,3}(=+|-+)\s*$")
TABLE_RULE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")


@dataclass
class Row:
    """One row of the rendered text: the characters, a style for each, and where the
    links are, as (start, end, url) in text."""
    text: str = ""
    styles: list = field(default_factory=list)
    links: list = field(default_factory=list)
    anchor: str = None # on a heading's first row: its #anchor, as GitHub makes them

    def __add__(self, other):
        shift = len(self.text)
        return Row(self.text + other.text, self.styles + other.styles,
                   self.links + [(a + shift, b + shift, url) for a, b, url in other.links])


def slug(heading):
    """A heading's anchor, as GitHub makes it: "Panels in a layout" -> "panels-in-a-layout"."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def _row(text, style=""):
    return Row(text, [style] * len(text))


# --- Blocks -------------------------------------------------------------------

def _starts_block(line):
    """True if a line starts something other than a paragraph (so it ends one)."""
    return bool(FENCE.match(line) or HEADING.match(line) or RULE.match(line) or QUOTE.match(line)
                or (ITEM.match(line) and line.strip() not in ("-", "*", "+")))


def parse(lines):
    """Lines of Markdown -> blocks: (kind, ...) tuples."""
    blocks, i = [], 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        indent = len(line) - len(line.lstrip(" "))
        if (match := FENCE.match(line)):
            fence, body = match.group(1), []
            i += 1
            while i < len(lines) and not re.match(rf"^ {{0,3}}{fence[0]}{{{len(fence)},}}\s*$", lines[i]):
                body.append(lines[i][min(indent, len(lines[i]) - len(lines[i].lstrip(" "))):])
                i += 1
            blocks.append(("code", body))
            i += 1
        elif indent >= 4:
            body = []
            while i < len(lines) and (not lines[i].strip() or lines[i].startswith("    ")):
                body.append(lines[i][4:])
                i += 1
            while body and not body[-1].strip(): body.pop()
            blocks.append(("code", body))
        elif (match := HEADING.match(line)):
            blocks.append(("heading", len(match.group(1)), match.group(2) or ""))
            i += 1
        elif RULE.match(line):
            blocks.append(("rule",))
            i += 1
        elif QUOTE.match(line):
            inner = []
            while i < len(lines) and lines[i].strip() and (QUOTE.match(lines[i]) or not _starts_block(lines[i])):
                inner.append(QUOTE.sub("", lines[i], count=1))
                i += 1
            blocks.append(("quote", parse(inner)))
        elif (match := ITEM.match(line)) and line.strip() not in ("-", "*", "+"):
            i = _parse_list(lines, i, blocks)
        elif "|" in line and i + 1 < len(lines) and TABLE_RULE.match(lines[i + 1]) and "-" in lines[i + 1]:
            rows = [line]
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(lines[i])
                i += 1
            blocks.append(("table", [_cells(row) for row in rows]))
        else:
            text = [line.strip()]
            breaks = [line.endswith("  ") or line.rstrip().endswith("\\")]
            i += 1
            while i < len(lines) and lines[i].strip() and not _starts_block(lines[i]):
                if SETEXT.match(lines[i]):
                    break
                text.append(lines[i].strip())
                breaks.append(lines[i].endswith("  ") or lines[i].rstrip().endswith("\\"))
                i += 1
            if i < len(lines) and (match := SETEXT.match(lines[i])):
                blocks.append(("heading", 1 if match.group(1)[0] == "=" else 2, " ".join(text)))
                i += 1
                continue
            joined = ""
            for n, (part, hard) in enumerate(zip(text, breaks)):
                if hard and part.endswith("\\"): part = part[:-1]
                joined += part + ("" if n == len(text) - 1 else "\n" if hard else " ")
            blocks.append(("paragraph", joined))
    return blocks


def _parse_list(lines, i, blocks):
    """A list starting at lines[i]: adds ("list", ordered, start, loose, items) and returns
    the line after it. Each item is (blocks, task) with task None, " " or "x"."""
    first = ITEM.match(lines[i])
    ordered = first.group(2)[0].isdigit()
    start = int(first.group(2)[:-1]) if ordered else 1
    items, loose = [], False
    def sibling(line): # the next item of this list: the same kind, not indented into this one
        match = ITEM.match(line or "")
        return bool(match) and match.group(2)[0].isdigit() == ordered and len(match.group(1)) < width
    width = 2
    while i < len(lines):
        match = ITEM.match(lines[i])
        if not match or match.group(2)[0].isdigit() != ordered:
            break
        width = len(match.group(0)) if match.group(3) else len(match.group(0)) + 1 # where the text starts
        body = [lines[i][len(match.group(0)):]]
        i += 1
        while i < len(lines):
            line = lines[i]
            if not line.strip():
                # A blank line: the item goes on if what follows is indented into it
                nxt = next((l for l in lines[i + 1:] if l.strip()), None)
                if nxt is None or len(nxt) - len(nxt.lstrip(" ")) < width:
                    if sibling(nxt): loose = True # blank lines between items
                    break
                body.append("")
                i += 1
                continue
            indent = len(line) - len(line.lstrip(" "))
            if indent >= width:
                body.append(line[width:])
            elif ITEM.match(line) or _starts_block(line):
                break
            else:
                body.append(line.strip()) # a lazy continuation of the paragraph
            i += 1
        task = None
        if (found := TASK.match(body[0])):
            task = found.group(1).lower()
            body[0] = body[0][found.end():]
        items.append((parse(body), task))
        while i < len(lines) and not lines[i].strip():
            if not sibling(next((l for l in lines[i:] if l.strip()), None)): break
            i += 1
    blocks.append(("list", ordered, start, loose, items))
    return i


def _cells(row):
    row = row.strip()
    if row.startswith("|"): row = row[1:]
    if row.endswith("|") and not row.endswith("\\|"): row = row[:-1]
    return [cell.strip().replace("\\|", "|") for cell in re.split(r"(?<!\\)\|", row)]


# --- Inline -------------------------------------------------------------------

def inline(text, base, theme):
    """Markdown inside a paragraph -> a Row (newlines kept, for hard breaks)."""
    out = Row()
    i, n = 0, len(text)
    plain = []
    def flush():
        nonlocal out
        if plain:
            out += _row("".join(plain), base)
            plain.clear()
    while i < n:
        char = text[i]
        if char == "\\" and i + 1 < n and not text[i + 1].isalnum() and text[i + 1] != " ":
            plain.append(text[i + 1])
            i += 2
        elif char == "&" and (entity := next((e for e in ENTITIES if text.startswith(e, i)), None)):
            plain.append(ENTITIES[entity])
            i += len(entity)
        elif char == "`":
            run = "`" * (len(text) - i - len(text[i:].lstrip("`"))) # `code`, or ``code with ` in it``
            close = text.find(run, i + len(run))
            if close < 0:
                plain.append(run)
                i += len(run)
                continue
            code = text[i + len(run):close].replace("\n", " ")
            if code.startswith(" ") and code.endswith(" ") and code.strip(): code = code[1:-1]
            flush()
            out += _row(code, base + theme.get("md_code", ""))
            i = close + len(run)
        elif char == "<" and (match := re.match(r"<((?:https?|mailto|ftp):[^\s>]+)>", text[i:])):
            flush()
            url = match.group(1)
            out += Row(url, [base + theme.get("md_link", "")] * len(url), [(0, len(url), url)])
            i += match.end()
        elif char == "!" and text.startswith("[", i + 1) and (link := _link(text, i + 1)):
            label, url, end = link
            flush()
            shown = f"[{label or 'image'}]"
            out += Row(shown, [base + theme.get("md_quote", "")] * len(shown), [(0, len(shown), url)])
            i = end
        elif char == "[" and (link := _link(text, i)):
            label, url, end = link
            flush()
            inner = inline(label, base + theme.get("md_link", ""), theme)
            out += Row(inner.text, inner.styles, [(0, len(inner.text), url)])
            i = end
        elif char in "*_~" and (span := _emphasis(text, i)):
            delim, inner_text, end = span
            flush()
            extra = {"***": BOLD + ITALIC, "___": BOLD + ITALIC, "**": BOLD, "__": BOLD,
                     "*": ITALIC, "_": ITALIC, "~~": STRIKE}[delim]
            out += inline(inner_text, base + extra, theme)
            i = end
        else:
            plain.append(char)
            i += 1
    flush()
    return out


def _link(text, i):
    """[label](url "title") at text[i]: (label, url, end), or None."""
    depth, j = 0, i
    while j < len(text):
        if text[j] == "\\": j += 2; continue
        if text[j] == "[": depth += 1
        elif text[j] == "]":
            depth -= 1
            if depth == 0: break
        j += 1
    else:
        return None
    match = re.match(r"\(\s*<?([^\s()<>]*(?:\([^\s()]*\)[^\s()<>]*)*)>?(?:\s+[\"'(].*?[\"')])?\s*\)", text[j + 1:])
    if not match: return None
    return text[i + 1:j], match.group(1), j + 1 + match.end()


def _emphasis(text, i):
    """**bold**, *italic*, ***both***, ~~struck~~ (and _ forms) at text[i]: (delimiter,
    inside, end), or None."""
    for delim in ("***", "___", "**", "__", "~~", "*", "_"):
        if not text.startswith(delim, i): continue
        start = i + len(delim)
        if start >= len(text) or text[start].isspace(): return None
        if delim[0] == "_" and i > 0 and text[i - 1].isalnum(): return None # snake_case words
        j = start + 1
        while True:
            j = text.find(delim, j)
            if j < 0: break
            after = j + len(delim)
            if not text[j - 1].isspace() and not (delim[0] == "_" and after < len(text) and text[after].isalnum()) \
                    and not text.startswith(delim[0], after): # not the start of a longer run
                return delim, text[start:j], after
            j += 1
        if delim not in ("*", "_"): continue # **x* : try * on its own
        return None
    return None


# --- Drawing --------------------------------------------------------------------

def render(source, width, theme):
    """Markdown -> the rows to draw, width wide."""
    lines = source.expandtabs(4).replace("\r\n", "\n").split("\n")
    return _blocks(parse(lines), max(4, width), "", theme, 0)


def _blocks(blocks, width, base, theme, depth, tight=False):
    """tight: no blank rows between the blocks (inside a list item with no blank lines)."""
    rows = []
    for n, block in enumerate(blocks):
        if n and not tight: rows.append(_row(""))
        rows.extend(_block(block, width, base, theme, depth))
    return rows


def _wrap(row, width):
    """A Row word-wrapped to width."""
    out = []
    for start, end in wrap_spans(row.text, width):
        links = [(max(a, start) - start, min(b, end) - start, url) for a, b, url in row.links if a < end and b > start]
        out.append(Row(row.text[start:end], row.styles[start:end], links))
    return out


def _block(block, width, base, theme, depth):
    kind = block[0]
    if kind == "paragraph":
        return _wrap(inline(block[1], base, theme), width)
    if kind == "heading":
        level = block[1]
        style = theme.get("md_heading1" if level == 1 else "md_heading2" if level == 2 else "md_heading", "")
        text = inline(block[2], base + style, theme)
        rows = _wrap(text, width)
        if rows: rows[0].anchor = slug(text.text)
        return rows
    if kind == "rule":
        return [_row("─" * width, theme.get("md_rule", ""))]
    if kind == "code":
        style = theme.get("md_code_block", "")
        rows = []
        for line in block[1] or [""]:
            line = line.replace("\t", "    ")
            while True: # hard-wrapped, so nothing's lost
                part, line = line[:width - 2], line[width - 2:]
                rows.append(_row(pad_right(f" {part}", width), style))
                if not line: break
        return rows
    if kind == "quote":
        bar = _row("│ ", theme.get("md_quote", ""))
        inner = _blocks(block[1], width - 2, base + theme.get("md_quote_text", ""), theme, depth)
        return [bar + row for row in inner] or [bar]
    if kind == "list":
        _, ordered, start, loose, items = block
        markers = [f"{start + n}." if ordered else BULLETS[depth % len(BULLETS)] for n in range(len(items))]
        pad = max(text_width(m) for m in markers) + 1
        rows = []
        for n, ((blocks, task), marker) in enumerate(zip(items, markers)):
            if n and loose: rows.append(_row(""))
            lead = _row(pad_right(marker, pad), theme.get("md_bullet", ""))
            if task is not None:
                lead = lead + _row("☑ " if task == "x" else "☐ ", theme.get("md_bullet", ""))
            inner = _blocks(blocks, width - len(lead.text), base, theme, depth + 1, tight=not loose) or [_row("")]
            rows.extend((lead if i == 0 else _row(" " * len(lead.text))) + row for i, row in enumerate(inner))
        return rows
    if kind == "table":
        return _table(block[1], width, base, theme)
    return []


def _table(raw_rows, width, base, theme):
    header, body = raw_rows[0], raw_rows[1:]
    columns = max(len(row) for row in raw_rows)
    cells = [[inline(row[c] if c < len(row) else "", base, theme) for c in range(columns)] for row in raw_rows]
    widths = [max(text_width(row[c].text) for row in cells) for c in range(columns)]
    while sum(widths) + 3 * (columns - 1) > width and max(widths) > 3: # shrink the widest to fit
        widths[widths.index(max(widths))] -= 1
    line = theme.get("md_rule", "")
    def draw(row, extra=""):
        out = Row()
        for c, (cell, w) in enumerate(zip(row, widths)):
            if c: out += _row(" │ ", line)
            text = fit(cell.text, w)
            out += Row(text, [s + extra for s in cell.styles[:len(text)]] + [base] * (len(text) - len(cell.styles)),
                       cell.links) + _row(" " * (w - text_width(text)), base)
        return out
    rows = [draw(cells[0], theme.get("md_table_header", ""))]
    rows.append(_row("─┼─".join("─" * w for w in widths), line))
    rows.extend(draw(row) for row in cells[1:])
    return rows
