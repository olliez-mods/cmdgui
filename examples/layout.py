from cmdgui.layout import parse_layout, place, LayoutError

layout = parse_layout("""
    button[a]  button[b]  stdout[log]{+b,w=10+}
    canvas{+b} -          |
    |          -          |
""")

# Normally the view gets these from the widget classes, with the layout's flags on top
sizes = {"a": ("5+", 1), "b": ("5+", 1), "log": ("10+", "3+")}
borders = {name: slot.flags.get("border", False) for name, slot in layout.slots.items()}

p = place(layout, 60, 16, sizes, borders)
print(f"needs at least {p.min_width}x{p.min_height}, fits on 60x16: {p.fits}\n")
for name, slot in layout.slots.items():
    x, y, w, h = p.rects[name]
    print(f"{name:7} {slot.type:7} x={x:<3} y={y:<3} w={w:<3} h={h:<3} border={borders[name]}")

# Mistakes give readable errors
for bad in ["text[a] text[b] a", "text[a]{+b} a{-b}", "text[a]{b}", "text[a]{w=wide}"]:
    try:
        parse_layout(bad)
    except LayoutError as e:
        print("\nerror:", e)
