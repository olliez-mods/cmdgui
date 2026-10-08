import random
import time
from cmdgui import View, Label, ProgressBar, Button, Stdout

# ProgressBar.track(): wrap your loop in it and the bar keeps up by itself, with how many
# are done and about how long is left. Your loop runs as normal, here in the main program.
# Cancel stops a loop early (the bar stays where it got to). q to quit.

FILES = [f"photo_{n:03}.jpg" for n in range(1, 41)]

def incoming():
    """A generator: it can't say how many there'll be, so the bar just counts."""
    for n in range(random.randint(25, 40)):
        yield f"message {n + 1}"

class App(View):
    layout = """
        heading  -
        copying  cancel{w=12}
        reading  -
        log      -
    """
    heading = Label("[bold]Two loops, two bars[/]  [dim]· q to quit[/]")
    copying = ProgressBar(title="copying photos", border=True)
    reading = ProgressBar(title="reading messages (no total)", border=True)
    cancel = Button("Cancel", on_click=lambda: stop.append(True))
    log = Stdout()

stop = []
view = App()

for name in view.copying.track(FILES):      # 12/40 · 8s left
    if stop: break                           # stopping early is fine
    time.sleep(random.uniform(0.05, 0.25))   # the work
    print(f"copied {name}")

stop.clear()
for message in view.reading.track(incoming()):
    if stop: break
    time.sleep(random.uniform(0.05, 0.2))
    print(f"read {message}")

print("all done")
view.wait()
