from cmdgui import View, Graphics, RadioGroup, Label
import math
import time

# Pixel graphics. The big picture is drawn by on_paint 30 times a second; switch its
# mode on the left to compare resolutions, and click it to make ripples.
# The sketch pad keeps what you draw: drag in it, press c to clear. q to quit.

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
    aspect = g.pixel_aspect  # quad pixels are twice as tall as wide: squash vertically to stay round
    cx, cy = w / 2, h / 2
    size = min(w, h * aspect)

    g.ellipse(cx, cy, size * 0.12, size * 0.12 / aspect, "gold", fill=True)
    for orbit, radius, speed, color in PLANETS:
        r = size * orbit
        g.ellipse(cx, cy, r, r / aspect, "dark_gray")
        x, y = cx + r * math.cos(t * speed), cy + r * math.sin(t * speed) / aspect
        g.ellipse(x, y, max(1, size * radius), max(1, size * radius) / aspect, color, fill=True)

    # A spinning star in the corner: one polygon, so its middle is a hole (even-odd fill)
    sx, sy, sr = size * 0.12 + 2, size * 0.12 / aspect + 2, size * 0.11
    points = [(sx + sr * math.cos(t + i * 4 * math.pi / 5), sy + sr * math.sin(t + i * 4 * math.pi / 5) / aspect)
              for i in range(5)]
    g.polygon(points, "hot_pink", fill=True)

    # A wave along the bottom
    swing = h * 0.25 * math.sin(t * 2)
    g.bezier([(0, h - 3), (w / 3, h - 3 - swing), (2 * w / 3, h - 3 + swing), (w - 1, h - 3)], "aqua")

    for ripple in ripples[:]:
        x, y, made = ripple
        r = (t - made) * size * 0.6
        if r > size * 0.5:
            ripples.remove(ripple)
            continue
        g.ellipse(x * w, y * h, r, r / aspect, "white" if r < size * 0.25 else "gray")

    g.view.info.text = f"{w}x{h} pixels in {g.width}x{g.height} cells"

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
    view.sketch.line(*pen["at"], x, y, COLORS[pen["color"]])
    pen["at"] = (x, y)

class Demo(View):
    layout = """
        mode    scene
        info    scene
        sketch  scene
    """
    mode = RadioGroup(["half", "quad", "braille"], border=True, preferred_width="26",
                      on_change=lambda index, mode: view.scene.set(mode=mode))
    info = Label()
    sketch = Graphics(title="sketch · c clears", background="charcoal", on_click=pen_down, on_drag=pen_move)
    scene = Graphics(background="navy", on_paint=paint, on_click=ripple)

view = Demo()
view.on_key("c", view.sketch.clear)
view.every(1 / 30, view.scene.repaint)
view.focus(view.mode)
view.wait()
