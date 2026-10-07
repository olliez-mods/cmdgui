from cmdgui import View, Graphics, RadioGroup, Label
import math
import time

# Pixel graphics. The big picture is drawn by on_paint 30 times a second; switch its
# mode on the left to compare resolutions, and click it to make ripples.
# Sextant needs a newer terminal, and octant a very new font: boxes mean no support.
# Press a to turn fix_aspect off and on: off, circles go tall and thin in quad mode.
# The sketch pad keeps what you draw: drag in it, press c to clear. q to quit.
# Drag the line left of the picture to make it bigger or smaller.

START = time.monotonic()
ripples = []  # (x, y as fractions of the picture, time made)
PLANETS = [   # (orbit, size, speed, color), sizes as fractions of the picture
    (0.22, 0.035, 1.6, "orange"),
    (0.33, 0.05, 1.0, "sky"),
    (0.45, 0.04, 0.6, "coral"),
]

def paint(g: Graphics):
    t = time.monotonic() - START
    w, h = g.pixel_width, g.pixel_height
    # Quad pixels are twice as tall as wide. Circles stay round by themselves (fix_aspect),
    # but positions are in pixels: a point r below the centre is r / aspect pixels down
    aspect = g.pixel_aspect if g.fix_aspect else 1
    cx, cy = w / 2, h / 2
    size = min(w, h * aspect)

    g.circle(cx, cy, size * 0.12, "gold", fill=True)
    for orbit, radius, speed, color in PLANETS:
        r = size * orbit
        g.circle(cx, cy, r, "dark_gray")
        x, y = cx + r * math.cos(t * speed), cy + r * math.sin(t * speed) / aspect
        g.circle(x, y, max(1, size * radius), color, fill=True)

    # A spinning star in the corner: one polygon, so its middle is a hole (even-odd fill)
    sx, sy, sr = size * 0.12 + 2, size * 0.12 / aspect + 2, size * 0.11
    points = [(sx + sr * math.cos(t + i * 4 * math.pi / 5), sy + sr * math.sin(t + i * 4 * math.pi / 5) / aspect)
              for i in range(5)]
    g.polygon(points, "hot_pink", fill=True)

    # A wave along the bottom
    swing = h * 0.25 * math.sin(t * 2)
    g.bezier([(0, h - 3), (w / 3, h - 3 - swing), (2 * w / 3, h - 3 + swing), (w - 1, h - 3)], "aqua", thickness=3)

    for ripple in ripples[:]:
        x, y, made = ripple
        r = (t - made) * size * 0.6
        if r > size * 0.5:
            ripples.remove(ripple)
            continue
        g.circle(x * w, y * h, r, "white" if r < size * 0.25 else "gray", thickness=2)

    # Text in the pixel font, centred along the top, and a clock in the corner
    title = g.mode.upper()
    scale = 2 if g.text_size(title, 2)[0] < w / 3 else 1
    g.text((w - g.text_size(title, scale)[0]) / 2, 2, title, "white", scale)
    g.text(2, h - 9, time.strftime("%H:%M:%S"), "light_gray")

    g.view.info.text = f"{w}x{h} pixels in {g.width}x{g.height} cells, fix_aspect {'on' if g.fix_aspect else 'off'}"

def ripple(x, y):
    g = view.scene
    ripples.append((x / g.pixel_width, y / g.pixel_height, time.monotonic() - START))

COLORS = ["lime", "aqua", "hot_pink", "gold", "violet"]
pen = {"at": None, "color": 0}

def pen_down(x, y):
    pen["at"] = (x, y)
    pen["color"] = (pen["color"] + 1) % len(COLORS)  # each stroke a new color
    view.sketch.pixel(x, y, COLORS[pen["color"]])

def pen_move(x, y):
    view.sketch.line(*pen["at"], x, y, COLORS[pen["color"]], thickness=2)
    pen["at"] = (x, y)

class Demo(View):
    layout = """
        mode    scene
        info    scene
        sketch  scene
    """
    mode = RadioGroup(["half", "quad", "sextant", "octant", "braille"], border=True, preferred_width="26",
                      on_change=lambda index, mode: view.scene.set(mode=mode))
    info = Label()
    sketch = Graphics(title="sketch · c clears", background="charcoal", on_click=pen_down, on_drag=pen_move)
    scene = Graphics(background="navy", on_paint=paint, on_click=ripple)

view = Demo()
view.adjustable([view.mode, view.info, view.sketch], view.scene) # a line to drag between them
view.on_key("c", view.sketch.clear)
view.on_key("a", lambda: view.scene.set(fix_aspect=not view.scene.fix_aspect))
view.every(1 / 30, view.scene.repaint)
view.focus(view.mode)
view.wait()
