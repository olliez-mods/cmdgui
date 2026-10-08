"""Group (named widgets arranged by a layout string), and the groups that are widgets:
Panel, and Popup, a panel that floats. View is a group too, in view.py."""
from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, Callable, Optional, TypeVar, Union
from .widgets.base import Widget, WIDGET_TYPES, Size, W, _groups
from .layout import pair_axis, parse_layout, parse_size, place, LayoutError

G = TypeVar("G", bound="Panel")

# Group attributes a panel sets as it's laid out; they don't redraw it like a widget's do
GROUP_ATTRS = {"widgets", "named", "frames", "layout", "grid"}


def _spec(preferred, natural):
    """A widget's size range, raised to fit its content if it has room to grow."""
    low, high = parse_size(preferred)
    if natural is not None:
        low = max(low, natural if high is None else min(natural, high))
    return f"{low}+" if high is None else f"{low}-{max(low, high)}"


def _size_specs(widget, fit_content, bordered):
    """The (width, height) sizes to give the layout for a widget: its preferred sizes,
    raised to what the widgets inside it need, and with fit_content to its content_size()."""
    need_w, need_h = widget._needed_size(fit_content, bordered)
    if fit_content:
        content_w, content_h = widget.content_size()
        content_w = content_w if need_w is None else need_w
        content_h = content_h if need_h is None else need_h
        return _spec(widget.preferred_width, content_w), _spec(widget.preferred_height, content_h)
    if need_w is not None or need_h is not None:
        return _spec(widget.preferred_width, need_w), _spec(widget.preferred_height, need_h)
    return widget.preferred_width, widget.preferred_height


def _min_size(widget, fit_content, bordered):
    """The smallest content (width, height) a widget can have."""
    width, height = _size_specs(widget, fit_content, bordered)
    return parse_size(width)[0], parse_size(height)[0]


def _clip(a, b):
    """Where two clip rectangles (x0, y0, x1, y1) overlap; None is no clip at all."""
    if a is None: return b
    if b is None: return a
    return max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])


def _put(widget, x, y, width, height, framed, clip=None, frame_clip=None):
    """Give a widget its rectangle (inside any border) and place what's inside it.
    framed: there's a border line around it, which a panel shares with the widgets in it.
    clip and frame_clip: where it and its border are cut off, inside a scrolled panel."""
    widget._framed = framed
    widget._clip, widget._parent_frame_clip = clip, frame_clip
    moved = (widget.x, widget.y, widget.width, widget.height) != (x, y, width, height)
    if moved:
        widget.x, widget.y, widget.width, widget.height = x, y, width, height
        widget._dirty = True
    widget._arrange_children() # even at the same size: something inside may have been hidden or shown
    if moved: widget.on_resize()


class _Line:
    """A draggable line from group.adjustable(), as a key in the group's frames: drawn
    with the borders, so it joins up with them."""
    title = _name = border_style = None
    def _border_shapes(self, frame):
        return {self: frame}, {}


class _EdgeLine:
    """A draggable line between two sides of a group's layout (see Group.adjustable).
    first and second are the sides' names in layout order: left or above first."""
    def __init__(self, axis, first, second):
        self.axis, self.first, self.second = axis, first, second
        # (kind, side, amount): "share" of the room or "cells", for side 0 (first) or 1
        # (second). None until set or dragged: where the grid puts it
        self.position = None
        self.callback = None # (function, flipped): flipped if it was given the sides swapped

    def copy(self):
        return copy.copy(self)


def _to_position(value, flipped):
    """A position as given (0.3, 30 or -30, for the side named first) -> (kind, side, amount)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"an edge's position is a fraction (0.3) or a number of cells (30, or -30), not {value!r}")
    side = 1 if flipped else 0
    if isinstance(value, float):
        if not 0 <= value <= 1: raise ValueError(f"a fraction for an edge's position goes from 0 to 1, not {value}")
        return "share", side, value
    return ("cells", 1 - side, -value) if value < 0 else ("cells", side, value)


def _from_position(position, flipped):
    """The other way: (kind, side, amount) -> the number for the side named first."""
    kind, side, amount = position
    mine = side == (1 if flipped else 0)
    if kind == "share": return amount if mine else 1 - amount
    return amount if mine else -amount


class Edge:
    """A draggable line between widgets, from group.adjustable() or group.edge().

    position is where it is, for the side named first: a fraction of the room (0.3), a
    number of cells (30), or a negative number of cells for the other side (-30 keeps
    that side 30 wide as the terminal resizes). Dragging keeps the same kind of number.
    Before it's set or dragged, it's where the layout put it, as a fraction."""
    def __init__(self, group: "Group", line: _EdgeLine, flipped: bool):
        self._group, self._line, self._flipped = group, line, flipped

    @property
    def position(self) -> Union[float, int, None]:
        line = self._line
        if line.position is not None: return _from_position(line.position, self._flipped)
        index = self._group._edges.index(line)
        if index not in self._group._spans: return None # not laid out yet, or a side is hidden
        _, start, room, _, _, at = self._group._spans[index]
        share = (at - start) / room if room > 0 else 0.5
        return 1 - share if self._flipped else share

    @position.setter
    def position(self, value: Union[float, int]) -> None:
        self._line.position = _to_position(value, self._flipped)
        self._group._relayout_soon()

    def on_change(self, callback: Optional[Callable[[Union[float, int]], Any]]) -> None:
        """Call callback(position) when the line is dragged. None to stop."""
        self._line.callback = (callback, self._flipped) if callback else None


class Group():
    """Named widgets arranged by a layout string. View and Panel (and so Tabs and
    Popup) are groups: widgets come from the layout, class attributes and keyword
    arguments, and are found with group.name, group["name"] or group.get("name", Kind)."""
    layout: Optional[str] = None # subclasses can set the layout here
    _kind = "group"              # for messages: "view", "panel", "popup", "tabs"

    def _init_group(self, layout, widgets):
        """Collect, check and create the widgets. Views run this before touching
        the terminal, so a mistake doesn't leave it in raw mode."""
        self.widgets: list[Widget] = []
        self.named: dict[str, Widget] = {} # name -> widget, for widgets from the layout
        self.frames: dict[Any, tuple[int, int, int, int]] = {} # widget (or line) -> border rectangle
        self._edges: list[_EdgeLine] = [] # the draggable lines, from adjustable()
        self._lines = {}     # edge index -> (x, y, w, h) on screen
        self._line_keys = {} # edge index -> its _Line, the key in frames
        self._spans = {}     # edge index -> (axis, start, room, low, high, at) on screen, see layout.Placement
        self._values_callback: Optional[Callable[[dict], Any]] = None # from on_values_change()

        # Class attributes (copied, so each instance gets its own) and keyword arguments
        provided: dict[str, Any] = {}
        for klass in reversed(type(self).__mro__):
            for name, value in vars(klass).items():
                if isinstance(value, Widget):
                    provided[name] = value.copy()
        for name, value in widgets.items():
            if not isinstance(value, Widget):
                raise TypeError(f"{type(self).__name__}() got an unexpected argument '{name}' "
                                f"(widgets must be Widget or Panel instances)")
            provided[name] = value
        for name in [name for name, value in provided.items() if isinstance(value, Popup)]:
            self._add_popup(name, provided.pop(name))

        self.layout = layout if layout is not None else type(self).layout or self._default_layout(provided)
        if provided and not self.layout:
            raise LayoutError(f"widgets were given ({', '.join(provided)}) but there's no layout to put them in")
        self.grid = parse_layout(self.layout, types=WIDGET_TYPES, names=provided) if self.layout else None
        if not self.grid:
            return
        unused = [name for name in provided if name not in self.grid.slots]
        if unused:
            raise LayoutError(f"widget{'s' if len(unused) > 1 else ''} {', '.join(unused)} "
                              f"{'are' if len(unused) > 1 else 'is'} not in the layout")
        for name, slot in self.grid.slots.items():
            # Something else of the same name: an attribute, or a method or setting of any
            # class it's built on (a widget class attribute hides those, so look at each)
            if name in self.__dict__ or any(name in vars(klass) and not isinstance(vars(klass)[name], Widget)
                                            for klass in type(self).__mro__):
                raise LayoutError(f"widget name '{name}' clashes with {self._kind}.{name}, pick another name")
            widget = provided.get(name)
            if widget is None:
                widget = WIDGET_TYPES[slot.type]()
            elif slot.type is not None and not isinstance(widget, WIDGET_TYPES[slot.type]):
                raise LayoutError(f"the layout says '{name}' is a {slot.type}, "
                                  f"but it was given a {type(widget).__name__}")
            for attr, value in (slot.flags or {}).items():
                if attr == "scrollable" and not isinstance(widget, Panel):
                    raise LayoutError(f"'{name}' is a {type(widget).__name__}: only panels scroll with {{+s}} "
                                      f"(put it in a Panel(scrollable=True))")
                setattr(widget, attr, value) # the layout's flags, like {+b,w=20}
            widget._name = name
            widget._group = self
            self.widgets.append(widget)
            self.named[name] = widget
        for name, widget in self.named.items():
            self.__dict__[name] = widget # group.name finds this instance's copy, not the class attribute

    def _add_popup(self, name, popup) -> None:
        raise TypeError(f"{type(self).__name__}() got a popup '{name}', only views can hold popups")

    def _default_layout(self, provided):
        """With no layout: the widgets one above the other, in the order they're declared
        (a single widget fills the space)."""
        return "\n".join(provided) or None

    def __getitem__(self, name: str) -> Any:
        return self.named[name]

    def get(self, name: str, kind: type[W]) -> W:
        """A widget (or panel) by name, typed for your editor: view.get("heading", Label)"""
        widget = self.named[name]
        if not isinstance(widget, kind):
            raise TypeError(f"'{name}' is a {type(widget).__name__}, not a {kind.__name__}")
        return widget

    def __getattr__(self, name):
        # Only called for attributes that don't exist, so view.start finds the widget "start"
        named = self.__dict__.get("named", {})
        if name in named:
            return named[name]
        raise AttributeError(f"{self._kind} has no attribute or widget named '{name}'")

    # --- Form values ---

    @property
    def values(self) -> dict:
        """What's in the inputs inside, by name: {"name": "Ada", "debug": True}. Inputs are
        text boxes, checkboxes and toggles, radio groups, selects, sliders, and dates; a
        panel (or Tabs) inside gives a dict of its own: {"profile": {"name": "Ada"}}.

        Set it to fill them in: panel.values = saved. Only the names given change, and
        like setting a widget's value, it doesn't call their on_change."""
        out = {}
        for name, widget in self.named.items():
            if isinstance(widget, Group):
                inner = widget.values
                if inner: out[name] = inner
            elif widget.form_input:
                out[name] = widget.value
        return out

    @values.setter
    def values(self, values: dict) -> None:
        for name, value in values.items():
            widget = self.named.get(name)
            if widget is None:
                raise KeyError(f"no input named {name!r} in this {self._kind} (inputs: {', '.join(self.values) or 'none'})")
            if isinstance(widget, Group):
                if not isinstance(value, dict):
                    raise TypeError(f"'{name}' is a {widget._kind} of inputs, so its value is a dict, not {value!r}")
                widget.values = value
            elif widget.form_input:
                widget.value = value
                if hasattr(widget, "cursor"): widget.set(cursor=len(str(value)), anchor=None) # text boxes: to the end
            else:
                raise TypeError(f"'{name}' is a {type(widget).__name__}, which doesn't have a value to set")

    def on_values_change(self, callback: Optional[Callable[[dict], Any]]) -> None:
        """Call callback(values) whenever an input inside changes: as it's edited, picked or
        ticked (when its own on_change is called). For saving as you go, or noticing
        unsaved changes: view.on_values_change(lambda values: save(values))."""
        self._values_callback = callback

    def _frame_title(self, key):
        """The title on the border of one of this group's widgets: its title, or its name.
        Just the title for a panel: its border is the widgets' inside too, and their titles go there."""
        return key.title if isinstance(key, Panel) else key.title or key._name

    def _frame_style(self, key):
        """The border style of one of this group's widgets, None for the view's."""
        return key.border_style

    def _place(self, width, height, fit_content=False, outer=False):
        """Work out where the widgets go in a width x height box (positions relative to it).
        fit_content: grow widgets to their content_size(); outer: leave room for a border around it all."""
        sizes, borders = {}, {}
        hidden = {name for name, widget in self.named.items() if not widget.visible}
        for name, widget in self.named.items():
            if name in hidden: continue
            borders[name] = widget.border
            sizes[name] = _size_specs(widget, fit_content, widget.border)
        return place(self.grid, width, height, sizes, borders, outer=outer, hidden=hidden,
                     pairs=[(line.axis, line.first, line.second) for line in self._edges],
                     positions={i: line.position for i, line in enumerate(self._edges)})

    def adjustable(self, first: Union[Widget, str, list], second: Union[Widget, str, list],
                   position: Union[float, int, None] = None,
                   on_change: Optional[Callable[[Union[float, int]], Any]] = None) -> Edge:
        """Put a line between two widgets that are next to each other in the layout, to
        drag with the mouse: view.adjustable(view.files, view.editor). Dragging shares
        the room between just those two; nothing else moves.

        They have to line up, side by side or one above the other, so together they
        form a rectangle. Either side can be a list of widgets stacked along the line,
        like [view.editor, view.log] next to view.files.

        position: where the line starts, for the first side: a fraction of the room
        (0.3), cells (30), or negative cells for the second side (-30). Without it, the
        line starts where the layout puts it. on_change(position) is called when it's
        dragged. Returns the Edge; calling this again for the same two changes it."""
        sides = [self._side(side) for side in (first, second)]
        if not self.grid: raise LayoutError(f"adjustable() needs widgets in the {self._kind}'s layout")
        axis, a, b = pair_axis(self.grid, *sides)
        line = next((line for line in self._edges if (set(line.first), set(line.second)) == (set(a), set(b))), None)
        if line is None:
            for other in self._edges:
                if other.axis != axis and not self._nested((a, b), (other.first, other.second)):
                    raise LayoutError("a widget can only have draggable lines both across and up and down "
                                      "if one pair is inside one side of the other")
            line = _EdgeLine(axis, a, b)
            self._edges.append(line)
        edge = Edge(self, line, flipped=set(a) != set(sides[0]))
        if position is not None: edge.position = position
        if on_change is not None: edge.on_change(on_change)
        self._relayout_soon()
        return edge

    def edge(self, first: Union[Widget, str, list], second: Union[Widget, str, list]) -> Edge:
        """The draggable line between two widgets, from adjustable(). One widget from each
        side is enough: view.edge(view.files, view.editor).position = 0.3 sets it, for
        the side named first."""
        a, b = set(self._side(first)), set(self._side(second))
        for line in self._edges:
            if a <= set(line.first) and b <= set(line.second): return Edge(self, line, flipped=False)
            if a <= set(line.second) and b <= set(line.first): return Edge(self, line, flipped=True)
        raise LookupError(f"no draggable line between {', '.join(sorted(a))} and {', '.join(sorted(b))}; "
                          f"make one with adjustable()")

    def _side(self, side):
        """The names of the widgets on one side of a draggable line."""
        names = []
        for item in side if isinstance(side, (list, tuple)) else [side]:
            name = item if isinstance(item, str) else \
                next((name for name, widget in self.named.items() if widget is item), None)
            if name not in self.named:
                raise LayoutError(f"{item!r} isn't in this {self._kind}'s layout")
            names.append(name)
        if not names: raise LayoutError("a side of a draggable line needs at least one widget")
        return names

    @staticmethod
    def _nested(pair, other):
        """True if the two pairs share no widgets, or one sits inside one side of the other."""
        a, b = set(pair[0] + pair[1]), set(other[0] + other[1])
        if not a & b: return True
        return any(a <= set(side) for side in other) or any(b <= set(side) for side in pair)

    def _relayout_soon(self):
        """Work the layout out again on the next frame, if it's being shown."""
        view = next((w.view for w in self.widgets if w.view), None)
        if view: view.relayout()

    def _place_lines(self, placement, x, y):
        """Record where the draggable lines went, offset to (x, y), and add them to frames."""
        self._lines, self._spans = {}, {}
        for i, (lx, ly, lw, lh) in (placement.lines or {}).items():
            line = self._line_keys.setdefault(i, _Line())
            self._lines[i] = (x + lx, y + ly, lw, lh)
            self.frames[line] = self._lines[i]
            axis, *along = placement.spans[i]
            offset = x if axis == "x" else y
            start, room, low, high, at = along
            self._spans[i] = (axis, start + offset, room, low + offset, high + offset, at + offset)


class Panel(Widget, Group):
    """A layout of widgets that's a widget itself: it goes in a cell of a layout, in a
    tab of a Tabs widget, or floats as a Popup.

        class Sidebar(Panel):
            layout = '''
                search
                results
            '''
            search = TextInput()
            results = Menu()

    Written just like a View subclass. Without a layout, the widgets go one above the
    other in the order they're declared, so a panel with one widget is just
    Panel(Menu(items)). Settings like border, title and visible work as for any widget.

    Panel is also the base for widgets that hold other widgets, like Tabs: the widgets
    are collected the same way, and a subclass overrides how they're placed and shown
    (_inside, _arrange_children, _needed_size).

    With scrollable=True (or {+s} in the layout) it can be shorter than its widgets need,
    and scrolls: with the mouse wheel over it (unless what's under the mouse scrolls
    itself, like a list), and to show whatever gets focus. scroll is how far down it is."""
    _kind = "panel"
    scrollable: bool = False # scroll when it's shorter than its widgets need
    _auto_type = False # Panel subclasses aren't layout types by their class name
    _needs = "a layout or at least one widget" # for the error when it's empty

    def __init__(self, layout: Union[str, Widget, None] = None, *,
                 border: Optional[bool] = None, title: Optional[str] = None, **kwargs: Any):
        widgets = {name: value for name, value in kwargs.items() if isinstance(value, Widget)}
        settings = {name: value for name, value in kwargs.items() if name not in widgets}
        if border is not None: settings["border"] = border
        if title is not None: settings["title"] = title
        self._setup()
        self.scroll = 0         # rows scrolled down, when scrollable
        self._viewport = None   # (x, y, width, height) on screen of what shows, while scrolling
        self._content_height = 0 # how tall its widgets need to be
        self._inner_clip = None  # where the widgets inside are cut off (see _put)
        self._frame_clip = None  # and their borders
        self._apply((), settings)
        self._unnamed = set() # names made up here, not shown as border titles
        if isinstance(layout, Widget):
            widgets = {"content": layout, **widgets}
            self._unnamed = {"content"}
            layout = None
        self._init_group(layout, widgets)
        if not self.grid:
            raise LayoutError(f"{type(self).__name__} needs {self._needs}")
        self.init()
        self._ready = True

    def init(self) -> None:
        """Override to wire up widgets, e.g. self.no.on_click(self.close)."""

    if not TYPE_CHECKING:
        def __setattr__(self, key, value):
            if key in GROUP_ATTRS: object.__setattr__(self, key, value)
            else: super().__setattr__(key, value)

    def copy(self: G) -> G:
        """A separate copy with its own widgets (init() runs again for it)."""
        new = super().copy()
        new.__dict__.update(widgets=[], named={}, frames={},
                            _edges=[line.copy() for line in self._edges], _lines={}, _line_keys={}, _spans={},
                            **self._copy_resets())
        for name, widget in self.named.items():
            widget = widget.copy()
            widget._name = name
            widget._group = new
            new.widgets.append(widget)
            new.named[name] = widget
            new.__dict__[name] = widget
        new.init()
        return new

    def _copy_resets(self) -> dict:
        return {"scroll": 0, "_viewport": None, "_inner_clip": None, "_frame_clip": None}

    def refresh(self):
        """Redraw it, and everything inside it, on the next frame."""
        super().refresh()
        for widget in self.widgets: widget.refresh()

    def _frame_title(self, key):
        return key.title if key._name in self._unnamed else key.title or key._name

    # --- As a widget ---
    def _inside(self, hidden=False):
        return self.widgets

    def _needed_size(self, fit_content, bordered):
        width, height = self._outer_size(fit_content, outer=bordered)
        if bordered: width, height = width - 2, height - 2 # our edge is the layout's border
        if self.scrollable and not fit_content:
            return width + 1, 1 # any height will do; and a column for the scroll bar
        return width, height

    def content_size(self):
        return self._needed_size(True, self.border)

    def _arrange_children(self):
        x, y, w, h = self.x, self.y, self.width, self.height
        self._viewport = None
        self._inner_clip, self._frame_clip = self._clip, self._parent_frame_clip
        if self.scrollable:
            framed = self._framed
            self._content_height = self._outer_size(False, outer=framed)[1] - (2 if framed else 0)
            if self._content_height > h: # too tall: lay it all out, and show a window onto it
                w = max(0, w - 1) # the scroll bar's column, on the right
                most = self._content_height - h
                if not 0 <= self.scroll <= most: object.__setattr__(self, "scroll", max(0, min(self.scroll, most)))
                self._viewport = (x, y, w, h)
                self._inner_clip = _clip(self._clip, (x, y, x + w, y + h))
                # Borders inside can join the panel's own border down the left, and along the
                # top or bottom only while scrolled right to that end (so nothing scrolled past
                # draws on it); the scroll bar's column is left to the scroll bar
                left = 1 if framed else 0
                top = 1 if framed and self.scroll == 0 else 0
                bottom = 1 if framed and self.scroll >= most else 0
                self._frame_clip = _clip(self._parent_frame_clip, (x - left, y - top, x + w, y + h + bottom))
                y, h = y - self.scroll, self._content_height
            elif self.scroll:
                object.__setattr__(self, "scroll", 0)
        if self._framed: # the border round it is the edge of our layout, shared with the widgets inside
            self._arrange(x - 1, y - 1, w + 2, h + 2, outer=True)
        else:
            self._arrange(x, y, w, h)

    def _draw_area(self):
        if self._viewport: # the scroll bar, in the last column
            return self.width - 1, 0, 1, self.height
        return 0, 0, 0, 0 # the widgets inside draw everything

    # --- Scrolling ---
    def _scroll_bar(self):
        """(top, size) of the scroll bar's thumb, in rows of the viewport, or None."""
        if not self._viewport: return None
        rows, total = self._viewport[3], self._content_height
        if rows <= 0: return None
        size = max(1, round(rows * rows / total))
        top = round(self.scroll / max(1, total - rows) * (rows - size))
        return top, size

    def draw(self, c):
        bar = self._scroll_bar()
        if bar is None: return
        top, size = bar
        for row in range(c.height):
            on = top <= row < top + size
            c.put(0, row, "█" if on else "░", self.theme("scrollbar" if on else "scrollbar_track"))

    def scroll_by(self, rows: int) -> bool:
        """Scroll down (or up, for negative rows), if it's scrolling. True if it moved."""
        if not self._viewport: return False
        scroll = max(0, min(self._content_height - self._viewport[3], self.scroll + rows))
        if scroll == self.scroll: return False
        self.scroll = scroll
        if self.view: self.view.relayout()
        return True

    def _reveal(self, widget):
        """Scroll so a widget inside is in view (as much of it as fits)."""
        if not self._viewport: return
        frames = widget._group.frames if widget._group is not None else {}
        bx, by, bw, bh = frames.get(widget) or (widget.x, widget.y, widget.width, widget.height)
        top = by - self._viewport[1] + self.scroll # in rows of the content
        rows = self._viewport[3]
        if top < self.scroll: self.scroll_by(top - self.scroll)
        elif top + min(bh, rows) > self.scroll + rows: self.scroll_by(top + min(bh, rows) - self.scroll - rows)

    # --- The layout inside ---
    def _outer_size(self, fit_content, outer):
        """The smallest (width, height) the panel's layout fits in."""
        placement = self._place(0, 0, fit_content=fit_content, outer=outer)
        return placement.min_width, placement.min_height

    def _arrange(self, x, y, w, h, fit_content=False, outer=False):
        """Place the widgets in the w x h box at (x, y). outer: the box's edge is a
        border line (drawn by whatever holds the panel), shared with the widgets' borders."""
        placement = self._place(w, h, fit_content=fit_content, outer=outer)
        inner = 1 if outer else 0
        self.frames = {self.named[name]: (x + fx, y + fy, fw, fh) for name, (fx, fy, fw, fh) in placement.frames.items()}
        self._place_lines(placement, x, y)
        for name, (rx, ry, rw, rh) in placement.rects.items():
            widget = self.named[name]
            # Clip to the inside of the box, in case it's too small
            rw = max(0, min(rw, w - inner - rx))
            rh = max(0, min(rh, h - inner - ry))
            _put(widget, x + rx, y + ry, rw, rh, framed=widget in self.frames,
                 clip=self._inner_clip, frame_clip=self._frame_clip)


class Popup(Panel):
    """A box that floats over the view, with its own layout of widgets:

        class Confirm(Popup):
            layout = '''
                message  -
                yes      no
            '''
            message = Label("Delete everything?")
            yes = Button("Yes")
            no = Button("No")

        view.show(Confirm())

    Without a layout, the widgets go one above the other in the order they're
    declared: Popup(Menu(items)) for a popup with one widget.
    Settings can be class attributes or constructor arguments. Once it's shown, x, y,
    width and height are where it is on screen, border included."""
    _kind = "popup"
    modal: bool = True                    # block everything underneath while open
    close_on_escape: bool = True
    close_on_outside_click: bool = False
    keep_typing: bool = False             # the focused text box keeps getting typed text; arrows and Enter come here
    border = True
    close_callback: Optional[Callable[[], Any]] = None
    _dialog = False # from view.confirm() and the like: key bindings wait until it's answered

    def __init__(self, layout: Union[str, Widget, None] = None, *,
                 modal: Optional[bool] = None, close_on_escape: Optional[bool] = None,
                 close_on_outside_click: Optional[bool] = None, keep_typing: Optional[bool] = None,
                 border: Optional[bool] = None, title: Optional[str] = None,
                 preferred_width: Size = None, preferred_height: Size = None,
                 on_close: Optional[Callable[[], Any]] = None, **widgets: Widget):
        settings = dict(modal=modal, close_on_escape=close_on_escape, keep_typing=keep_typing,
                        close_on_outside_click=close_on_outside_click, close_callback=on_close,
                        preferred_width=preferred_width, preferred_height=preferred_height)
        self._anchor: tuple[str, Any] = ("center", None)
        self._previous_focus: Optional[Widget] = None
        super().__init__(layout, border=border, title=title,
                         **{key: value for key, value in settings.items() if value is not None}, **widgets)

    @property
    def is_open(self) -> bool:
        return self.view is not None

    def on_close(self, callback: Optional[Callable[[], Any]]) -> None:
        """Call callback() whenever the popup closes."""
        self.close_callback = callback

    def close(self) -> None:
        """Close the popup (does nothing if it isn't open)."""
        if self.view: self.view._close(self)

    def _copy_resets(self) -> dict:
        return {"_previous_focus": None}

    def _frame_title(self, key):
        return key.title # names aren't shown in popups

    def _contains(self, x, y):
        return self.x <= x < self.x + self.width and self.y <= y < self.y + self.height
