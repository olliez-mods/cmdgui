from __future__ import annotations

from .base import Widget, WIDGET_TYPES


class Container(Widget):
    """A widget that holds panels of other widgets, like Tabs. This does the
    bookkeeping; subclasses place, show and draw the panels (see the container methods
    on Widget: _visible_panels, _arrange_children, _needed_size and so on).

    The panels come from, in order:
        class attributes of a subclass   files = Files()      (each instance gets copies)
        keyword arguments                Tabs(files=Files())
        positional arguments             (if positional_names)

    Each can be a Panel or a single widget, which is put in a panel of its own.
    container.name finds the panel, or the widget if it was given on its own, and
    container.panels has them all by name, in order."""

    # Class settings (not constructor arguments, so not annotated)
    panel_count = (1, None)     # the fewest and most panels, None for no limit
    panel_kind = "panel"        # what a panel is called in messages, e.g. "tab"
    positional_names = ()       # names for panels passed in order; they aren't attributes
    widget_titles = False       # a widget given on its own has its name as its border title

    def __init__(self, *args, **kwargs):
        from ..view import Panel # here, because view.py imports the widgets
        given = {}
        for klass in reversed(type(self).__mro__):
            for name, value in vars(klass).items():
                if isinstance(value, (Panel, Widget)):
                    given[name] = value.copy()
        for name in [name for name, value in kwargs.items() if isinstance(value, (Panel, Widget))]:
            given[name] = kwargs.pop(name)
        items = [arg for arg in args if isinstance(arg, (Panel, Widget))]
        args = [arg for arg in args if not isinstance(arg, (Panel, Widget))]
        if len(items) > len(self.positional_names):
            raise TypeError(f"{type(self).__name__}() takes {len(self.positional_names) or 'no'} "
                            f"{self.panel_kind}s in order, got {len(items)}; pass them by name")
        given.update(zip(self.positional_names, items))
        low, high = self.panel_count
        if len(given) < low or (high is not None and len(given) > high):
            wanted = f"exactly {low}" if low == high else f"at least {low}" if high is None else f"{low} to {high}"
            raise ValueError(f"{type(self).__name__} needs {wanted} {self.panel_kind}{'s' if (high or low) != 1 else ''}, "
                             f"got {len(given)}")
        wrapped = {name for name, item in given.items() if isinstance(item, Widget)}
        object.__setattr__(self, "panels", {})
        self._add_panels({name: self._wrap(name, item) if name in wrapped else item for name, item in given.items()},
                         wrapped)
        super().__init__(*args, **kwargs)

    def _wrap(self, name, widget):
        """A panel holding just this widget."""
        from ..view import Panel
        if self.widget_titles and name not in self.positional_names:
            return Panel(**{name: widget}) # named, so the name is its title, as in a view's layout
        return Panel(widget)

    def _add_panels(self, panels, wrapped):
        from ..view import Panel
        self._wrapped = wrapped # names given as widgets, not panels
        for name, panel in panels.items():
            if name not in self.positional_names:
                # A method or setting of the same name, like show or position
                if any(name in vars(klass) and not isinstance(vars(klass)[name], (Panel, Widget))
                       for klass in type(self).__mro__):
                    raise ValueError(f"{self.panel_kind} name '{name}' clashes with "
                                     f"{type(self).__name__}.{name}, pick another name")
                # container.name finds this instance's copy, not the class attribute
                self.__dict__[name] = panel.named[next(iter(panel.named))] if name in wrapped else panel
            panel._container = self
            self.panels[name] = panel

    def copy(self):
        new = super().copy()
        object.__setattr__(new, "panels", {})
        new._add_panels({name: panel.copy() for name, panel in self.panels.items()}, self._wrapped)
        return new

    def _panels(self):
        return list(self.panels.values())

del WIDGET_TYPES["container"] # not a widget to put in a layout by itself
