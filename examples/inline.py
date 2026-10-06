from cmdgui import View, Label, ProgressBar, Button
import random
import time

# An inline view: it draws in a few rows under your prompt instead of taking over the
# screen. What the program prints appears above it, and when it finishes, the last frame
# stays in your terminal's scrollback. Press c (or click Cancel) to stop early.

FILES = ["photos.zip", "notes.md", "song.flac", "backup.tar"]

class Downloads(View):
    layout = """
        heading   -          -
        name0     bar0       -
        name1     bar1       -
        name2     bar2       -
        name3     bar3       -
        status    .          cancel
    """
    heading = Label("[bold]Downloading[/] [dim]· c to cancel[/]")
    name0, name1, name2, name3 = (Label(f"[cyan]{name}[/]", preferred_width=12) for name in FILES)
    bar0, bar1, bar2, bar3 = (ProgressBar() for _ in FILES)
    status = Label("[dim]starting…[/]")
    cancel = Button("Cancel", on_click=lambda: cancelled.append(True))

cancelled = []
view = Downloads(inline=True, quit_key=None)   # True: as many rows as the layout needs
view.on_key("c", lambda: cancelled.append(True))
bars = [view.bar0, view.bar1, view.bar2, view.bar3]
done = set()

while view.running and not cancelled and len(done) < len(FILES):
    for i, bar in enumerate(bars):
        if i in done: continue
        bar.value = min(1.0, bar.value + random.uniform(0, 0.05))
        if bar.value >= 1:
            done.add(i)
            print(f"finished {FILES[i]}")   # printed above the view, like normal output
    view.status.text = f"[green]{len(done)}[/] of {len(FILES)} done"
    time.sleep(0.05)

view.status.text = "[bold green]all done ✓[/]" if len(done) == len(FILES) else "[yellow]cancelled[/]"
time.sleep(0.2)   # let the last frame draw
view.stop()       # the view stays on screen, and your prompt comes back below it
