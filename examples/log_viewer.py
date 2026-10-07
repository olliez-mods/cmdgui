from cmdgui import View, Panel, Log, RadioGroup, TextInput, Button, Stdout
import logging
import random
import threading
import time

# A log viewer. Drag the lines between the controls, the log and the prints to resize them. Pick a level to hide the less important messages, and
# type in the search box to find some. q to quit (when not typing).

class Controls(Panel):
    layout = """
        level
        search
        clear
        .
    """
    level = RadioGroup(["debug", "info", "warning", "error", "critical"], title="level", border=True,
                       on_change=lambda index, level: view.log.set(level=level))
    search = TextInput(placeholder="search", title="search",
                       suggest=["database", "finished", "polling", "request", "slow"],  # Tab completes
                       on_change=lambda text: view.log.set(search=text))
    clear = Button("Clear", on_click=lambda: view.log.clear())

class App(View):
    layout = """
        controls{+b} log{+b}
        |            prints{+b}
    """
    controls = Controls()    # a panel, placed like a widget
    log = Log(markup=True)   # messages can be styled: [bold]...[/]
    prints = Stdout()

view = App()
view.adjustable(view.controls, [view.log, view.prints], position=24)  # the controls are 24 wide
view.adjustable(view.log, view.prints, position=-6)                   # prints keep 6 rows, the log gets the rest

# Python's logging goes to the Log widget, from any thread
logger = logging.getLogger("worker")
logger.setLevel(logging.DEBUG)
logger.addHandler(view.log.handler())

def work():
    events = [
        (logging.DEBUG, "polling queue"), (logging.DEBUG, "cache hit for user [cyan]%d[/]"),
        (logging.INFO, "request from user [cyan]%d[/] served"), (logging.INFO, "job [bold]%d[/] finished"),
        (logging.WARNING, "job [bold]%d[/] is slow, took [yellow]2.4s[/]"),
        (logging.ERROR, "couldn't reach the database for job [bold]%d[/]"),
        (logging.CRITICAL, "disk full while saving job [bold]%d[/]"),
    ]
    while view.running:
        level, message = random.choices(events, weights=[8, 6, 6, 4, 2, 1, 0.3])[0]
        logger.log(level, message.replace("%d", str(random.randint(1, 999))))
        if random.random() < 0.05:
            print("printed text goes to the bottom panel")
        time.sleep(random.uniform(0.05, 0.5))

threading.Thread(target=work, daemon=True).start()
view.wait()
