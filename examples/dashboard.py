"""Mission Control: a live dashboard for a (simulated) fleet of services.

    python examples/dashboard.py        (best in a terminal of at least 100x32)

Arrows / click     pick a service           d  deploy      r  restart
Tab                move between widgets     s  scale       i  cause an incident
/                  command palette          ?  help        q  quit

Everything visual lives in the classes below. The bottom of the file is
the "real program": a simulation loop that only changes data and widget
attributes, while the view redraws itself on its own thread.
"""
import random
import time
from typing import Any, Callable, Optional

from cmdgui import (View, Popup, Widget, Label, Text, Button, TextInput, ProgressBar,
                    Checkbox, Toggle, Menu, Table, Log, field, style)
from cmdgui.shorts import escape, fit, pad_left, pad_right, text_width


# --- The data ---------------------------------------------------------------

class Service:
    def __init__(self, name, version, replicas, cpu, mem, rps):
        self.name, self.version, self.replicas = name, version, replicas
        self.status = "up"                # up, degraded, down, deploying, restarting
        self.base = (cpu, mem, rps)       # what its metrics hover around
        self.cpu = [cpu] * 60             # history, newest last
        self.mem = [mem] * 60
        self.rps = [rps] * 60
        self.started = time.time() - random.randint(600, 90000)
        self.errors = 0
        self.down_since: Optional[float] = None

    def __str__(self):
        return self.name

SERVICES = [
    Service("api",       "1.14.2", 3, 38, 52, 1200),
    Service("auth",      "2.3.0",  2, 21, 34, 640),
    Service("payments",  "0.9.7",  2, 27, 61, 180),
    Service("search",    "3.1.1",  4, 55, 72, 900),
    Service("mailer",    "1.0.4",  1, 9,  18, 40),
    Service("cdn-edge",  "5.2.0",  6, 44, 40, 4800),
]


def log(kind, service, message):
    # The Log widget adds the time and a coloured level; markup colours the rest
    level, mark = {"info": ("info", " "), "ok": ("info", "[green]✔[/]"),
                   "warn": ("warning", "[yellow]▲[/]"), "error": ("error", "[red]✖[/]")}[kind]
    view.log.add(f"{mark} [cyan]{service:<9}[/] {escape(message)}", level=level)


def uptime(service):
    if service.status == "down": return "—"
    seconds = int(time.time() - service.started)
    hours, minutes = seconds // 3600, seconds // 60 % 60
    return f"{hours}h {minutes:02}m" if hours else f"{minutes}m {seconds % 60:02}s"


# --- Custom widgets ---------------------------------------------------------

STATUS = {  # status -> (symbol, colour)
    "up": ("●", "green"), "degraded": ("●", "yellow"), "down": ("●", "red"),
    "deploying": ("◆", "cyan"), "restarting": ("◆", "cyan"),
}


class Banner(Widget):
    """A coloured bar across the top: a title on the left, a summary on the right."""
    left: str = field(default="", kw_only=False)
    right: str = ""
    preferred_height = 1

    def draw(self, c):
        bar = style(fg="black", bg="cyan")
        c.fill(style=bar)
        c.text(0, 0, fit(self.left, c.width), style(fg="black", bg="cyan", bold=True))
        right = self.right + " "
        if text_width(self.left) + text_width(right) < c.width:
            c.text(c.width - text_width(right), 0, right, bar)


class Sparkline(Widget):
    """A bar chart of recent values, newest on the right, coloured by threshold."""
    values: list = field(default_factory=list)
    unit: str = ""
    max_value: Optional[float] = None   # None: scale to the biggest value shown
    warn: Optional[float] = None        # yellow from here
    crit: Optional[float] = None        # red from here
    border = True
    preferred_height = "4+"

    BLOCKS = " ▁▂▃▄▅▆▇█"

    def draw(self, c):
        if not self.values or c.height < 2: return
        rows = c.height - 1  # the last row is the caption
        shown = self.values[-c.width:]
        top = self.max_value or max(max(shown), 1)
        start = c.width - len(shown)
        for i, value in enumerate(shown):
            s = self._colour(value)
            eighths = round(max(0, min(value, top)) / top * rows * 8)
            for row in range(rows):
                c.put(start + i, rows - 1 - row, self.BLOCKS[max(0, min(8, eighths - row * 8))], s)
        now, peak = self.values[-1], max(shown)
        caption = f"now {self._fmt(now)}{self.unit}"
        right = f"peak {self._fmt(peak)}{self.unit}"
        c.text(0, rows, fit(caption, c.width), self._colour(now) + style(bold=True))
        if text_width(caption) + text_width(right) + 2 <= c.width:
            c.text(c.width - text_width(right), rows, right, self.theme("dim"))

    def _colour(self, value):
        if self.crit is not None and value >= self.crit: return style(fg="red")
        if self.warn is not None and value >= self.warn: return style(fg="yellow")
        return style(fg="green")

    @staticmethod
    def _fmt(value):
        return f"{value / 1000:.1f}k" if value >= 1000 else f"{value:.0f}"


class ServiceList(Menu):
    """A Menu of services with a coloured status dot and their CPU, which also
    reports when the highlighted service changes (not just on Enter)."""
    change_callback: Optional[Callable[[Any], Any]] = field(default=None, alias="on_change")
    preferred_width = "24"

    def on_input(self, input):
        before = self.selected
        super().on_input(input)
        if self.selected != before and self.change_callback and self.items:
            self.change_callback(self.items[self.selected])

    def draw(self, c):
        if self.selected < self.scroll: object.__setattr__(self, "scroll", self.selected)
        if self.selected >= self.scroll + c.height: object.__setattr__(self, "scroll", self.selected - c.height + 1)
        for row, service in enumerate(self.items[self.scroll:self.scroll + c.height]):
            highlighted = self.scroll + row == self.selected
            base = self.theme("selected" if self.focused else "selected_unfocused") if highlighted else ""
            symbol, colour = STATUS[service.status]
            c.text(0, row, pad_right("", c.width), base)
            c.put(1, row, symbol, base if highlighted else style(fg=colour))
            c.text(3, row, fit(service.name, c.width - 9), base)
            cpu = "—" if service.status == "down" else f"{service.cpu[-1]:.0f}%"
            c.text(c.width - 5, row, pad_left(cpu, 4), base or self.theme("dim"))


# --- Popups -----------------------------------------------------------------

class Confirm(Popup):
    """A reusable yes/no dialog: confirm.ask(view, title, message, action)."""
    layout = """
        message  message
        yes      no
    """
    message = Text(align="center")
    yes = Button("Confirm")
    no = Button("Cancel")

    def init(self):
        self.action: Optional[Callable[[], Any]] = None
        self.no.on_click(self.close)
        self.yes.on_click(self._confirmed)

    def ask(self, view, title, message, action):
        self.title, self.message.text, self.action = title, message, action
        view.show(self)

    def _confirmed(self):
        self.close()
        if self.action: self.action()


class DeployDialog(Popup):
    """Pick a version and options, then watch the rollout. The deploy itself runs
    in the simulation loop; this just shows its progress."""
    layout = """
        info      info
        version   version
        migrate   canary
        progress  progress
        step      step
        go        cancel
    """
    title = "Deploy"
    info = Label()
    version = TextInput(placeholder="new version, e.g. 1.15.0", title="version", prefix="v")
    migrate = Checkbox("run migrations", checked=True)
    canary = Checkbox("canary first")
    progress = ProgressBar(preferred_width="40")
    step = Label(style=style(fg="bright_black"))
    go = Button("Deploy")
    cancel = Button("Cancel")

    def init(self):
        self.service: Optional[Service] = None
        self.deploying = False
        self.cancelled = False
        self.go.on_click(self._start)
        self.version.on_submit(lambda _: self._start())
        self.cancel.on_click(self._cancel)

    def open(self, view, service):
        if self.deploying:
            return view.show(self)  # already running: just bring it back
        self.service, self.cancelled = service, False
        self.info.text = f"[bold]{service.name}[/]  ·  currently [cyan]v{service.version}[/]  ·  {service.replicas} replicas"
        major, minor, patch = service.version.split(".")
        self.version.set(value=f"{major}.{minor}.{int(patch) + 1}", cursor=99)
        self.progress.value = 0
        self.step.text = "Enter: deploy   Esc: cancel"
        self.go.text, self.cancel.text = "Deploy", "Cancel"
        self.close_on_escape = True
        view.show(self)

    def _start(self):
        if self.deploying: return
        if self.progress.value >= 1: return self.close()  # "Done" button
        if not self.version.value.strip():
            self.step.text = "[red]✖ enter a version first[/]"
            return
        self.deploying = True
        self.close_on_escape = False  # don't lose the dialog mid-rollout
        self.go.text, self.cancel.text = "Deploying…", "Abort"
        start_task(deploy_task(self.service, self.version.value.strip(), self))

    def _cancel(self):
        if self.deploying: self.cancelled = True
        else: self.close()

    def finished(self, ok, message):
        self.deploying = False
        self.close_on_escape = True
        self.step.text = message
        self.go.text, self.cancel.text = ("Done", "Close") if ok else ("Retry", "Close")
        if not ok: self.progress.value = 0


class ScaleMenu(Popup):
    """A dropdown under the Scale button."""
    choices = Menu([f"{n} replica{'s' if n > 1 else ''}" for n in range(1, 9)],
                   on_select=lambda index, _: scale(index + 1))
    modal = False
    close_on_outside_click = True


class Palette(Popup):
    """The / command menu above the command line. Typing keeps going to the
    text box; arrows and Enter pick a command."""
    commands = Menu(border=False, on_select=lambda _, item: run_command(item))
    modal = False
    keep_typing = True
    close_on_outside_click = True


HELP = (__doc__ or "").split("\n\n")[2] + ("\n\n[bold]Commands[/] [dim](type / in the command line, Tab completes)[/]\n"
                                           "deploy · restart · scale · incident · heal · clear · help · quit")

class Help(Popup):
    title = "Help"
    text = Text(HELP)
    close_on_outside_click = True


# --- The view ---------------------------------------------------------------

THEME = {
    "border": style(fg="blue"),
    "border_focus": style(fg="magenta", bold=True),
    "title": style(fg="cyan", bold=True),
    "selected": style(fg="black", bg="magenta"),
    "selected_unfocused": style(fg="magenta", bold=True),
    "header": style(fg="cyan", bold=True),
    "button_focus": style(fg="magenta", bold=True),
    "button_hover": style(fg="black", bg="cyan"),
    "progress": style(fg="magenta"),
    "cursor": style(fg="black", bg="magenta"),
}


class MissionControl(View):
    layout = """
        banner    banner    banner    clock
        services  fleet     fleet     fleet
        services  cpu       mem       rps
        services  log       log       log
        deploy    restart   scale     heal
        command   -         -         -
    """
    banner = Banner(" ◆ MISSION CONTROL   prod-eu-1")
    clock = Label(align="right", preferred_width="10+", style=style(fg="black", bg="cyan", bold=True))
    services = ServiceList(SERVICES, title="services",
                           on_change=lambda service: show_service(service))
    fleet = Table(["service", "status", "version", "replicas", "uptime", "cpu", "mem", "req/s"],
                  preferred_height=len(SERVICES) + 1, markup=True)   # coloured statuses
    cpu = Sparkline(unit="%", max_value=100, warn=70, crit=90, preferred_height="5")
    mem = Sparkline(unit="%", max_value=100, warn=75, crit=90, preferred_height="5")
    rps = Sparkline(unit="/s", preferred_height="5")
    log = Log(markup=True, preferred_height="4+")
    deploy = Button("Deploy  d", on_click=lambda: view.deploy_dialog.open(view, selected()))
    restart = Button("Restart  r", on_click=lambda: ask_restart())
    scale = Button("Scale  s", on_click=lambda: view.show(view.scale_menu, below=view.scale))
    heal = Toggle("auto-heal", checked=True,
                  on_change=lambda on: log("info", "fleet", f"auto-heal {'on' if on else 'off'}"))
    command = TextInput(title="command", placeholder="/ for commands · type a service name to jump to it",
                        prefix="› ", suggest=lambda text: suggest_command(text),
                        on_change=lambda value: command_typed(value),
                        on_submit=lambda value: command_entered(value))

    confirm = Confirm()
    deploy_dialog = DeployDialog()
    scale_menu = ScaleMenu()
    palette = Palette()
    help = Help()


# --- What the UI does -------------------------------------------------------

COMMANDS = {
    "deploy":   "deploy a new version of the selected service",
    "restart":  "restart the selected service",
    "scale":    "change the number of replicas",
    "incident": "take a random service down",
    "heal":     "toggle auto-heal",
    "clear":    "clear the log",
    "help":     "show keys and commands",
    "quit":     "leave Mission Control",
}

def suggest_command(text):
    """The dim completion in the command line, which Tab fills in."""
    if text.startswith("/"):
        return next(("/" + name for name in COMMANDS if name.startswith(text[1:])), None)
    return next((s.name for s in SERVICES if s.name.startswith(text)), None)

def selected() -> Service:
    return SERVICES[view.services.selected]

def show_service(service):
    for widget, label in ((view.cpu, "cpu"), (view.mem, "memory"), (view.rps, "requests")):
        widget.title = f"{label} · {service.name}"
    refresh_charts()

def ask_restart():
    service = selected()
    view.confirm.ask(view, f"Restart {service.name}?",
                     f"All {service.replicas} replicas of [bold]{service.name}[/] will restart\n"
                     f"one at a time. [dim]Traffic keeps flowing.[/]",
                     lambda: start_task(restart_task(service)))

def scale(replicas):
    view.scale_menu.close()
    service = selected()
    if replicas != service.replicas:
        log("info", service.name, f"scaling {service.replicas} → {replicas} replicas")
        service.replicas = replicas

def command_typed(value):
    if value.startswith("/"):
        word = value[1:].strip()
        matches = [f"{name:<9}{help}" for name, help in COMMANDS.items() if name.startswith(word)]
        if matches:
            view.palette.commands.set(items=matches, selected=0)
            view.show(view.palette, above=view.command)
            return
    view.palette.close()
    # Not a command: jump to the first service whose name starts with what's typed
    match = next((i for i, s in enumerate(SERVICES) if value and s.name.startswith(value)), None)
    if match is not None and match != view.services.selected:
        view.services.selected = match
        show_service(SERVICES[match])

def command_entered(value):
    if value.startswith("/") and value[1:].strip() in COMMANDS:
        run_command(value[1:].strip())
    elif value.strip():
        log("warn", "console", f"unknown command '{value}' (type / to see commands)")
    view.command.value = ""

def run_command(item):
    name = item.split()[0]
    view.palette.close()
    view.command.value = ""
    actions = {
        "deploy": lambda: view.deploy_dialog.open(view, selected()),
        "restart": ask_restart,
        "scale": lambda: view.show(view.scale_menu, below=view.scale),
        "incident": incident,
        "heal": lambda: view.heal.toggle(),
        "clear": view.log.clear,
        "help": lambda: view.show(view.help),
        "quit": view.quit,
    }
    actions[name]()

def incident():
    victims = [s for s in SERVICES if s.status in ("up", "degraded")]
    if not victims: return
    service = random.choice(victims)
    service.status, service.down_since = "down", time.time()
    service.errors += random.randint(20, 200)
    log("error", service.name, "health checks failing — service is DOWN")
    if not view.heal.checked:
        view.alert(f"[bold red]{service.name} is down![/]\n\nAuto-heal is off. Restart it with [bold]r[/],\nor turn auto-heal on.",
                   title="⚠ Incident")


# --- Background work: deploys and restarts as small step-by-step tasks ------

tasks = [] # [generator, time to resume]

def start_task(generator):
    tasks.append([generator, 0.0])

def deploy_task(service, version, dialog):
    steps = [("Building image", 1.5), ("Pushing to registry", 1.0)]
    if dialog.migrate.checked: steps.append(("Running migrations", 1.0))
    if dialog.canary.checked: steps.append(("Canary at 10% of traffic", 2.0))
    steps += [(f"Rolling out replica {i + 1}/{service.replicas}", 0.7) for i in range(service.replicas)]
    steps.append(("Health checks", 1.0))
    total, done = sum(seconds for _, seconds in steps), 0.0
    old_status, service.status = service.status, "deploying"
    log("info", service.name, f"deploying v{service.version} → v{version}")
    for name, seconds in steps:
        dialog.step.text = f"{name}…"
        log("info", service.name, name.lower())
        for _ in range(int(seconds * 10)):
            if dialog.cancelled:
                service.status = old_status
                log("warn", service.name, f"deploy of v{version} aborted, rolled back")
                dialog.finished(False, "[yellow]▲ aborted[/] — rolled back")
                return
            yield 0.1
            done += 0.1
            dialog.progress.value = min(1.0, done / total)
    service.version, service.status = version, "up"
    service.started = time.time()
    log("ok", service.name, f"v{version} is live")
    dialog.finished(True, f"[green]✔ v{version} is live[/] on all {service.replicas} replicas")

def restart_task(service):
    service.status = "restarting"
    for i in range(service.replicas):
        log("info", service.name, f"restarting replica {i + 1}/{service.replicas}")
        yield 0.8
    service.status, service.down_since = "up", None
    service.started = time.time()
    log("ok", service.name, "restarted")


# --- The simulation (your "real program") ------------------------------------

def update_metrics():
    for s in SERVICES:
        cpu, mem, rps = s.base
        busy = s.status in ("up", "degraded", "deploying", "restarting")
        if s.status == "degraded": cpu += 35
        if s.status in ("deploying", "restarting"): cpu += 15
        def walk(history, target, spread, limit=None):
            value = history[-1] + (target - history[-1]) * 0.3 + random.gauss(0, spread)
            value = max(0, value if limit is None else min(limit, value))
            history.append(value if busy else 0)
            del history[:-120]
        walk(s.cpu, cpu, 4, 100)
        walk(s.mem, mem, 1.5, 100)
        walk(s.rps, rps * (1 + 0.3 * random.random()), rps * 0.05)

def random_events():
    for s in SERVICES:
        if s.status == "up" and random.random() < 0.004:
            s.status = "degraded"
            log("warn", s.name, "latency above 500ms, CPU climbing")
        elif s.status == "degraded" and random.random() < 0.05:
            s.status = "up"
            log("ok", s.name, "latency back to normal")
        elif s.status == "down" and view.heal.checked and time.time() - (s.down_since or 0) > 3:
            log("info", s.name, "auto-heal: restarting")
            start_task(restart_task(s))
            s.down_since = float("inf")  # only once
    if random.random() < 0.002:
        incident()

def refresh_charts():
    service = selected()
    view.cpu.set(values=list(service.cpu))
    view.mem.set(values=list(service.mem))
    view.rps.set(values=list(service.rps))

def refresh_overview():
    view.clock.text = time.strftime("%H:%M:%S ")
    counts = {status: sum(s.status == status for s in SERVICES) for status in STATUS}
    busy = counts["deploying"] + counts["restarting"]
    view.banner.right = (f"{counts['up']} up · {counts['degraded']} degraded · {counts['down']} down"
                         + (f" · {busy} busy" if busy else "") + "    ? help")
    view.fleet.rows = [[s.name, "[{1}]{0} {2}[/]".format(*STATUS[s.status], s.status), f"v{s.version}", s.replicas, uptime(s),
                        "—" if s.status == "down" else f"{s.cpu[-1]:.0f}%", f"{s.mem[-1]:.0f}%",
                        f"{s.rps[-1]:.0f}"] for s in SERVICES]
    view.services.refresh()


view = MissionControl(theme=THEME)
view.on_key("d", lambda: view.deploy_dialog.open(view, selected()))
view.on_key("r", ask_restart)
view.on_key("s", lambda: view.show(view.scale_menu, below=view.scale))
view.on_key("i", incident)
view.on_key("?", lambda: view.show(view.help))
view.on_key("/", lambda: (view.focus(view.command), view.command.set(value="/", cursor=1), command_typed("/")))
view.focus(view.services)
show_service(selected())

log("ok", "fleet", f"connected to prod-eu-1 · {len(SERVICES)} services")
log("info", "fleet", "press ? for help, / for commands")

last_metrics = 0.0
while view.running:
    with view.lock:  # change data and widgets together, so a frame never shows half an update
        now = time.time()
        for task in tasks[:]:
            if now >= task[1]:
                try:
                    task[1] = now + next(task[0])
                except StopIteration:
                    tasks.remove(task)
        if now - last_metrics >= 0.5:
            last_metrics = now
            update_metrics()
            random_events()
            refresh_charts()
        refresh_overview()
    time.sleep(0.1)
