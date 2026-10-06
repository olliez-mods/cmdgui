from cmdgui import View, Panel, Split, Log, RadioGroup, TextInput, Button, Stdout
import logging
import random
import threading
import time

# A log viewer. Drag the line between the panels (or focus it with Tab and use the
# arrow keys) to resize them. Pick a level to hide the less important messages, and
# type in the search box to find some. q to quit (when not typing).

class Controls(Panel):
    layout = """
        level
        search
        clear
        .
    """
    level = RadioGroup(["debug", "info", "warning", "error", "critical"], title="level", border=True,
                       on_change=lambda index, level: view.main.messages.log.set(level=level))
    search = TextInput(placeholder="search", title="search",
                       on_change=lambda text: view.main.messages.log.set(search=text))
    clear = Button("Clear", on_click=lambda: view.main.messages.log.clear())

class Messages(Split):
    vertical = True          # the log above, prints below
    position = -6            # prints keep 6 rows, the log gets the rest
    log = Log()
    prints = Stdout()

class Main(Split):
    position = 24            # the controls are 24 wide, the logs get what's left
    controls = Controls()
    messages = Messages()    # a split inside a split

class App(View):
    layout = "main"
    main = Main()

view = App()

# Python's logging goes to the Log widget, from any thread
logger = logging.getLogger("worker")
logger.setLevel(logging.DEBUG)
logger.addHandler(view.main.messages.log.handler())

def work():
    events = [
        (logging.DEBUG, "polling queue"), (logging.DEBUG, "cache hit for user %d"),
        (logging.INFO, "request from user %d served"), (logging.INFO, "job %d finished"),
        (logging.WARNING, "job %d is slow, took 2.4s"), (logging.ERROR, "couldn't reach the database for job %d"),
        (logging.CRITICAL, "disk full while saving job %d"),
    ]
    while view.running:
        level, message = random.choices(events, weights=[8, 6, 6, 4, 2, 1, 0.3])[0]
        logger.log(level, message.replace("%d", str(random.randint(1, 999))))
        if random.random() < 0.05:
            print("printed text goes to the bottom panel")
        time.sleep(random.uniform(0.05, 0.5))

threading.Thread(target=work, daemon=True).start()
view.wait()
