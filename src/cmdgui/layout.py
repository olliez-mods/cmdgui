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


def pair_axis(layout, first, second):
    """Check two sides (lists of widget names) can have a draggable line between them,
    and say which way it's dragged: "x" when they're side by side, "y" when stacked.
    Returns (axis, first, second), swapped if second comes first.

    Together the two sides must form a rectangle, so dragging only changes them.
    A side with more than one widget is a stack along the line: each of its widgets
    reaches all the way from the line to the side's far edge."""
    def describe(names):
        return names[0] if len(names) == 1 else "[" + ", ".join(names) + "]"

    def box(names):
        """(top, left, bottom, right) of the side, in grid cells (bottom, right exclusive)."""
        slots = [layout.slots[name] for name in names]
        top, left = min(s.row for s in slots), min(s.col for s in slots)
        bottom, right = max(s.row + s.rowspan for s in slots), max(s.col + s.colspan for s in slots)
        if sum(s.rowspan * s.colspan for s in slots) != (bottom - top) * (right - left):
            raise LayoutError(f"{describe(names)} doesn't form a rectangle, so it can't be one side of a draggable line")
        return top, left, bottom, right

    def span(top, left, bottom, right, axis):
        kind, low, high = ("row", top, bottom) if axis == "x" else ("column", left, right)
        return f"{kind} {low + 1}" if high - low == 1 else f"{kind}s {low + 1}-{high}"

    if set(first) & set(second):
        raise LayoutError(f"{', '.join(sorted(set(first) & set(second)))} can't be on both sides of a draggable line")
    a, b = box(first), box(second)
    if (b[3] == a[1] and b[0::2] == a[0::2]) or (b[2] == a[0] and b[1::2] == a[1::2]): # second comes first
        first, second, a, b = second, first, b, a
    if a[3] == b[1] and a[0::2] == b[0::2]:
        axis = "x"
    elif a[2] == b[0] and a[1::2] == b[1::2]:
        axis = "y"
    elif a[3] == b[1] or b[3] == a[1]:
        raise LayoutError(f"{describe(first)} and {describe(second)} have to line up to drag the line between them: "
                          f"{describe(first)} covers {span(*a, 'x')}, {describe(second)} {span(*b, 'x')}")
    elif a[2] == b[0] or b[2] == a[0]:
        raise LayoutError(f"{describe(first)} and {describe(second)} have to line up to drag the line between them: "
                          f"{describe(first)} covers {span(*a, 'y')}, {describe(second)} {span(*b, 'y')}")
    else:
        raise LayoutError(f"{describe(first)} and {describe(second)} aren't next to each other")
    for names, (top, left, bottom, right) in ((first, a), (second, b)):
        for name in names:
            s = layout.slots[name]
            whole = (s.col, s.col + s.colspan) == (left, right) if axis == "x" else (s.row, s.row + s.rowspan) == (top, bottom)
            if not whole:
                raise LayoutError(f"'{name}' doesn't fill the width of its side of the draggable line"
                                  if axis == "x" else
                                  f"'{name}' doesn't fill the height of its side of the draggable line")
    return axis, first, second


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
    lines: dict = None # pair index -> (x, y, w, h) of its draggable line
    spans: dict = None # pair index -> (axis, start, room, low, high, at) along the axis, for dragging:
                       # the room the pair has, the line's limits, and where it is


def place(layout, width, height, sizes=None, borders=None, outer=False, hidden=(), pairs=(), positions=None):
    """Work out where every widget goes on a width x height screen.

    sizes:   name -> (width spec, height spec), see parse_size
    borders: name -> True if the widget has a border
    outer:   always leave room for a border around the whole layout (popups)
    hidden:  names of widgets that take no room: rows and columns that only they
             cover shrink to nothing, and get no rects or frames
    pairs:   (axis, first names, second names) with a draggable line between them, see pair_axis
    positions: pair index -> where its line goes, (kind, side, amount): kind "share" for a
             fraction of the room (0 to 1), or "cells"; side 0 for the first side's size,
             1 for the second's. Without one, the line goes where the grid puts it.

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
    # Pairs with a draggable line between them (hidden widgets left out), and room for
    # both sides' minimums plus the line, even with no border line there in the grid
    pairs = [(i, axis, [n for n in first if n not in hidden], [n for n in second if n not in hidden])
             for i, (axis, first, second) in enumerate(pairs)]
    pairs = [(i, axis, first, second) for i, axis, first, second in pairs if first and second]
    col_items = [(s.col, s.colspan, *specs[s.name][0]) for s in slots]
    row_items = [(s.row, s.rowspan, *specs[s.name][1]) for s in slots]
    for _, axis, first, second in pairs:
        k = 0 if axis == "x" else 1
        ends = [(s.col, s.col + s.colspan) if axis == "x" else (s.row, s.row + s.rowspan)
                for s in (layout.slots[n] for n in first + second)]
        start, end = min(a for a, _ in ends), max(b for _, b in ends)
        need = max(specs[n][k][0] for n in first) + max(specs[n][k][0] for n in second) + 1
        (col_items if axis == "x" else row_items).append((start, end - start, need, None))
    col_widths, min_width = _size_tracks(width, layout.cols, col_lines, col_items, gone_cols)
    row_heights, min_height = _size_tracks(height, layout.rows, row_lines, row_items, gone_rows)
    col_x = _starts(col_widths, col_lines)
    row_y = _starts(row_heights, row_lines)

    rects = {}
    for s in slots:
        x, y = col_x[s.col], row_y[s.row]
        last_col, last_row = s.col + s.colspan - 1, s.row + s.rowspan - 1
        w = col_x[last_col] + col_widths[last_col] - x
        h = row_y[last_row] + row_heights[last_row] - y
        rects[s.name] = [x, y, w, h]
    lines, spans = _place_pairs(rects, pairs, specs, positions or {})
    frames = {name: (x - 1, y - 1, w + 2, h + 2) for name, (x, y, w, h) in rects.items() if borders.get(name)}
    edges = list(frames.values()) + list(lines.values()) + ([(0, 0, width, height)] if outer else [])
    lines = {i: _reach(line, spans[i][0], edges) for i, line in lines.items()}
    rects = {name: tuple(rect) for name, rect in rects.items()}
    return Placement(rects, frames, min_width, min_height, width >= min_width and height >= min_height,
                     lines, spans)


def _place_pairs(rects, pairs, specs, positions):
    """Move the line between each pair to its position, changing only the widgets
    either side of it. rects (name -> [x, y, w, h]) are changed in place. Returns each
    pair's line (x, y, w, h), and its spans (see Placement).

    A position is measured in the room the grid gave the pair, so moving one line
    doesn't move another that shares a widget with it."""
    grid = {name: rect[:] for name, rect in rects.items()} # before any lines moved
    lines, spans = {}, {}
    for i, axis, first, second in pairs:
        k, j = (0, 1) if axis == "x" else (1, 0) # along the drag, and across it
        start = min(grid[n][k] for n in first)
        end = max(grid[n][k] + grid[n][k + 2] for n in second)
        room = end - start - 1 # for the two sides, less the line
        at = max(grid[n][k] + grid[n][k + 2] for n in first) # just after the first side, as the grid has it
        if positions.get(i):
            kind, side, amount = positions[i]
            size = round(amount * room) if kind == "share" else amount
            at = start + (size if side == 0 else room - size)
        # Each side keeps its minimum (a maximum, like w=24, is only where the line starts)
        low = max(rects[n][k] + specs[n][k][0] for n in first)
        high = min(rects[n][k] + rects[n][k + 2] - 1 - specs[n][k][0] for n in second)
        at = max(low, min(high, at))
        for n in first:
            rects[n][k + 2] = max(0, at - rects[n][k])
        for n in second:
            far = rects[n][k] + rects[n][k + 2]
            rects[n][k], rects[n][k + 2] = at + 1, max(0, far - at - 1)
        across = min(rects[n][j] for n in first + second)
        length = max(rects[n][j] + rects[n][j + 2] for n in first + second) - across
        lines[i] = (at, across, 1, length) if axis == "x" else (across, at, length, 1)
        spans[i] = (axis, start, room, low, high, at)
    return lines, spans


def _reach(line, axis, edges):
    """Make a line one cell longer at each end where it meets a border or another line,
    so they join up."""
    def on_edge(px, py):
        return any((px in (x, x + w - 1) and y <= py < y + h) or (py in (y, y + h - 1) and x <= px < x + w)
                   for x, y, w, h in edges if (x, y, w, h) != line)
    x, y, w, h = line
    if axis == "x": # a line dragged sideways goes up and down
        if on_edge(x, y - 1): y, h = y - 1, h + 1
        if on_edge(x, y + h): h += 1
    else:
        if on_edge(x - 1, y): x, w = x - 1, w + 1
        if on_edge(x + w, y): w += 1
    return x, y, w, h


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
