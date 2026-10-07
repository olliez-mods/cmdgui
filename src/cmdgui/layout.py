import re
from dataclasses import dataclass

# type, type[name], with optional flags on the end: name{+b,w=20}
TOKEN = re.compile(r"^([A-Za-z_]\w*)(?:\[([A-Za-z_]\w*)\])?(?:\{([^{}]*)\})?$")
# a size: "5" exactly, "5+" at least, "5-10" between
SIZE = re.compile(r"^(\d+)(?:(\+)|-(\d+))?$")

EMPTY = "."
SPAN_LEFT = "-"
SPAN_UP = "|"


class LayoutError(ValueError):
    pass


# The border styles, for b=style
BORDER_STYLES = ("single", "rounded", "heavy", "double", "ascii")
# Flags that switch something on (+) or off (-), and the widget attribute they set
SWITCHES = {"b": "border", "e": "enabled", "f": "tab_stop", "v": "visible"}
FLAG_HELP = "+b/-b border, b=style, w=size, h=size, +e/-e enabled, +f/-f in Tab order, +v/-v shown, t=title"


def parse_flags(text, where=""):
    """The widget attributes set by a cell's flags: "+b,w=20" -> {"border": True, "preferred_width": 20}."""
    attrs = {}
    prefix = f"{where}: " if where else ""
    for flag in (part.strip() for part in text.split(",")):
        if not flag:
            continue
        if flag in ("b", "nb"):
            raise LayoutError(f"{prefix}{{{flag}}} is now {{{'+b' if flag == 'b' else '-b'}}}")
        if flag[0] in "+-" and flag[1:] in SWITCHES:
            attrs[SWITCHES[flag[1:]]] = flag[0] == "+"
            continue
        key, equals, value = flag.partition("=")
        if equals and key in ("w", "h"):
            parse_size(value, where)  # check it now
            attrs["preferred_width" if key == "w" else "preferred_height"] = int(value) if value.isdigit() else value
        elif equals and key == "b":
            if value not in BORDER_STYLES:
                raise LayoutError(f"{prefix}unknown border style '{value}' (use {', '.join(BORDER_STYLES)})")
            attrs["border"], attrs["border_style"] = True, value
        elif equals and key == "t":
            attrs["title"] = value.replace("_", " ")
        else:
            raise LayoutError(f"{prefix}unknown flag '{flag}' (flags: {FLAG_HELP})")
    return attrs


@dataclass
class Slot:
    name: str
    type: str  # None when the layout just names a widget that was passed in
    row: int
    col: int
    rowspan: int = 1
    colspan: int = 1
    flags: dict = None   # widget attributes set by the cell's flags, e.g. {"border": True}


@dataclass
class Layout:
    rows: int
    cols: int
    slots: dict  # name -> Slot, in the order they were declared


def parse_layout(text, types=None, names=()):
    """Parse a layout string into a Layout.

    types is an optional collection of known type names; if given, unknown
    types are an error. names are widgets provided by the caller: a bare word
    matching one of them refers to that widget instead of a type."""
    lines = [line.split() for line in text.splitlines() if line.strip()]
    if not lines: raise LayoutError("layout is empty")

    cols = len(lines[0])
    for r, cells in enumerate(lines):
        if len(cells) != cols:
            raise LayoutError(f"row {r + 1} has {len(cells)} cells, but row 1 has {cols}")

    slot_types = {}  # name -> type, in declaration order
    slot_flags = {}  # name -> widget attributes from its flags
    grid = [[None] * cols for _ in lines]  # name in each cell, None for empty

    for r, cells in enumerate(lines):
        for c, token in enumerate(cells):
            where = f"row {r + 1}, column {c + 1}"

            if token == EMPTY: continue

            if token == SPAN_LEFT:
                if c == 0: raise LayoutError(f"{where}: '-' has nothing to its left")
                if grid[r][c - 1] is None: raise LayoutError(f"{where}: '-' can't extend an empty cell")
                grid[r][c] = grid[r][c - 1]
                continue

            if token == SPAN_UP:
                if r == 0: raise LayoutError(f"{where}: '|' has nothing above it")
                if grid[r - 1][c] is None: raise LayoutError(f"{where}: '|' can't extend an empty cell")
                grid[r][c] = grid[r - 1][c]
                continue

            match = TOKEN.match(token)
            if not match:
                raise LayoutError(f"{where}: can't understand '{token}'")
            type_, name, flag = match.groups()
            if name is None and type_ in slot_types:  # repeat of an existing name: span
                if flag is not None:
                    raise LayoutError(f"{where}: put {{{flag}}} on the first '{type_}' cell, not a repeat")
                grid[r][c] = type_
                continue
            if name is None:
                name = type_
                if name in names:
                    type_ = None # a provided widget, no type needed
            elif name in slot_types:
                raise LayoutError(f"{where}: '{name}' is already declared; repeat it as just '{name}' to span")

            if types is not None and type_ is not None and type_ not in types:
                known = ", ".join(sorted(types))
                raise LayoutError(f"{where}: unknown widget type '{type_}' (known: {known})")
            slot_types[name] = type_
            slot_flags[name] = parse_flags(flag, where) if flag is not None else {}
            grid[r][c] = name

    return Layout(len(lines), cols, _build_slots(grid, slot_types, slot_flags))


def _build_slots(grid, slot_types, slot_flags):
    """Turn the grid of names into Slots, checking each name covers a rectangle."""
    cells = {}  # name -> list of (row, col)
    for r, row in enumerate(grid):
        for c, name in enumerate(row):
            if name is not None:
                cells.setdefault(name, []).append((r, c))

    slots = {}
    for name, type_ in slot_types.items():
        rows = [r for r, _ in cells[name]]
        cols = [c for _, c in cells[name]]
        top, left = min(rows), min(cols)
        rowspan, colspan = max(rows) - top + 1, max(cols) - left + 1
        if len(cells[name]) != rowspan * colspan:
            hint = f"; to add a second {type_}, give it its own name: {type_}[other_name]" if type_ else ""
            raise LayoutError(f"'{name}' doesn't form a rectangle{hint}")
        slots[name] = Slot(name, type_, top, left, rowspan, colspan, slot_flags[name])
    return slots


def parse_size(spec, where=""):
    """Turn a size into (min, max), max None for no limit.
    5 or "5" exactly, "5+" at least 5, "5-10" between, None flexible (at least 1)."""
    if spec is None:
        return 1, None
    if isinstance(spec, int):
        return spec, spec
    match = SIZE.match(str(spec).strip())
    if not match:
        raise LayoutError(f"{where + ': ' if where else ''}bad size '{spec}' (use e.g. 5, '5+' or '5-10')")
    low, plus, high = match.groups()
    low = int(low)
    if plus:
        return low, None
    if high is not None:
        if int(high) < low:
            raise LayoutError(f"{where + ': ' if where else ''}bad size '{spec}': max is smaller than min")
        return low, int(high)
    return low, low


@dataclass
class Placement:
    rects: dict    # name -> (x, y, width, height) of the widget's content
    frames: dict   # name -> (x, y, width, height) of the border, for bordered widgets
    min_width: int # smallest screen the layout fits on
    min_height: int
    fits: bool     # False if the screen is smaller than that


def place(layout, width, height, sizes=None, borders=None, outer=False, hidden=()):
    """Work out where every widget goes on a width x height screen.

    sizes:   name -> (width spec, height spec), see parse_size
    borders: name -> True if the widget has a border
    outer:   always leave room for a border around the whole layout (popups)
    hidden:  names of widgets that take no room: rows and columns that only they
             cover shrink to nothing, and get no rects or frames

    Border lines sit between grid rows/columns and are shared by neighbours,
    so two bordered widgets next to each other have one line between them."""
    sizes = sizes or {}
    borders = borders or {}
    every = list(layout.slots.values())
    slots = [s for s in every if s.name not in hidden]
    specs = {s.name: [parse_size(spec) for spec in sizes.get(s.name, (None, None))] for s in slots}

    # Rows and columns with hidden widgets in them collapse, as long as every shown widget
    # keeps some room (tracks with nothing in them stay flexible)
    gone = [s for s in every if s.name in hidden]
    gone_cols = _collapsed([(s.col, s.colspan) for s in gone], [(s.col, s.colspan) for s in slots])
    gone_rows = _collapsed([(s.row, s.rowspan) for s in gone], [(s.row, s.rowspan) for s in slots])
    col_lines = _lines(layout.cols, [(s.col, s.colspan) for s in slots if borders.get(s.name)], gone_cols)
    row_lines = _lines(layout.rows, [(s.row, s.rowspan) for s in slots if borders.get(s.name)], gone_rows)
    if outer:
        col_lines[0] = col_lines[-1] = row_lines[0] = row_lines[-1] = 1
    col_widths, min_width = _size_tracks(width, layout.cols, col_lines,
                                         [(s.col, s.colspan, *specs[s.name][0]) for s in slots], gone_cols)
    row_heights, min_height = _size_tracks(height, layout.rows, row_lines,
                                           [(s.row, s.rowspan, *specs[s.name][1]) for s in slots], gone_rows)
    col_x = _starts(col_widths, col_lines)
    row_y = _starts(row_heights, row_lines)

    rects, frames = {}, {}
    for s in slots:
        x, y = col_x[s.col], row_y[s.row]
        last_col, last_row = s.col + s.colspan - 1, s.row + s.rowspan - 1
        w = col_x[last_col] + col_widths[last_col] - x
        h = row_y[last_row] + row_heights[last_row] - y
        rects[s.name] = (x, y, w, h)
        if borders.get(s.name):
            frames[s.name] = (x - 1, y - 1, w + 2, h + 2)
    return Placement(rects, frames, min_width, min_height, width >= min_width and height >= min_height)


def _collapsed(hidden, shown):
    """The tracks (rows or columns) that take no room: the ones hidden widgets are in,
    except where that would leave a shown widget with none at all. A shown widget
    spanning a collapsed track just gets smaller."""
    gone = {i for start, span in hidden for i in range(start, start + span)}
    changed = True
    while changed:
        changed = False
        for start, span in shown:
            tracks = set(range(start, start + span))
            if tracks <= gone: # it would vanish: keep its tracks
                gone -= tracks
                changed = True
    return gone


def _lines(count, spans, gone=()):
    """Thickness (0 or 1) of the border line before each track, plus one after the last.
    Across a run of collapsed tracks, the lines either side become one."""
    lines = [0] * (count + 1)
    for start, span in spans:
        lines[start] = lines[start + span] = 1
    i = 0
    while i < count:
        if i in gone:
            end = i
            while end + 1 < count and end + 1 in gone: end += 1
            keep = max(lines[i:end + 2])
            lines[i:end + 2] = [keep] + [0] * (end + 1 - i)
            i = end + 1
        else:
            i += 1
    return lines


def _size_tracks(total, count, lines, items, gone=()):
    """Size the rows (or columns). items are (start, span, min, max) per widget.
    gone: tracks that take no room. Returns the sizes and the minimum total needed."""
    # Each track's range comes from the widgets that sit only in that track
    mins = [0] * count
    maxs = [0 if i in gone else None for i in range(count)]
    single = [[] for _ in range(count)]
    for start, span, low, high in items:
        if span == 1:
            single[start].append((low, high))
    for i, ranges in enumerate(single):
        if ranges:
            mins[i] = max(low for low, _ in ranges)
            # A widget with a size limit limits its track; flexible neighbours adapt
            highs = [high for _, high in ranges if high is not None]
            maxs[i] = max(min(highs), mins[i]) if highs else None

    # Spanning widgets: if their tracks are too small together, grow one of them
    for start, span, low, high in items:
        if span > 1:
            covered = sum(mins[start:start + span]) + sum(lines[start + 1:start + span])
            if covered < low:
                tracks = range(start, start + span)
                grow = next((i for i in reversed(tracks) if maxs[i] is None), tracks[-1])
                mins[grow] += low - covered
                if maxs[grow] is not None:
                    maxs[grow] = max(maxs[grow], mins[grow])

    # Everyone starts at their min, then the rest is shared equally between
    # tracks that can still grow, in rounds, until it runs out or all are full
    sizes = mins[:]
    remaining = total - sum(lines) - sum(sizes)
    while remaining > 0:
        growable = [i for i in range(count) if maxs[i] is None or sizes[i] < maxs[i]]
        if not growable:
            break
        share = remaining // len(growable)
        if share == 0:
            for i in growable[:remaining]:
                sizes[i] += 1
            break
        for i in growable:
            add = share if maxs[i] is None else min(share, maxs[i] - sizes[i])
            sizes[i] += add
            remaining -= add
    return sizes, sum(mins) + sum(lines)


def _starts(sizes, lines):
    """Start position of each track, leaving room for the border lines."""
    starts, pos = [], 0
    for i, size in enumerate(sizes):
        pos += lines[i]
        starts.append(pos)
        pos += size
    return starts
