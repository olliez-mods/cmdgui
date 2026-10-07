from cmdgui import View, Button, Menu, Stdout

# Dialogs that wait for an answer: view.confirm(), view.prompt() and view.choose() return
# what was picked, so there's no callback to write. They work from your own code (like the
# question at the start) and from callbacks (the buttons, and the keys d, r and o).
# Escape cancels. q to quit.

def selected():
    files = view.files
    return files.items[files.selected] if files.items else None

def delete():
    name = selected()
    if name is None: return
    if view.confirm(f"Delete [bold]{name}[/]? This can't be undone.", title="Delete", yes="Delete"):
        view.files.items.remove(name)
        view.files.selected = max(0, min(view.files.selected, len(view.files.items) - 1))
        view.files.refresh()  # the list was changed in place
        print(f"deleted {name}")
        view.notify(f"Deleted [bold]{name}[/]", "ok")  # a notification in the corner
    else:
        print(f"kept {name}")

def rename():
    name = selected()
    if name is None: return
    new = view.prompt("Rename to:", value=name, title="Rename")
    if new and new != name:
        view.files.items[view.files.selected] = new
        view.files.refresh()
        print(f"renamed {name} to {new}")
        view.notify(f"Renamed to [bold]{new}[/]", "ok")

def open_with():
    name = selected()
    if name is None: return
    app = view.choose(["vim", "nano", "VS Code", "less"], f"Open {name} with:", title="Open with")
    print(f"opening {name} in {app}" if app else "not opened")

class App(View):
    layout = """
        files{+b}  delete
        |          rename
        |          open
        |          .
        log{+b}    -
    """
    files = Menu(["notes.txt", "todo.md", "photo.png", "budget.csv"], title="files")
    delete = Button("Delete  d", on_click=delete)
    rename = Button("Rename  r", on_click=rename)
    open = Button("Open with  o", on_click=open_with)
    log = Stdout()

view = App()
view.on_key("d", delete)
view.on_key("r", rename)
view.on_key("o", open_with)

# From your own code: this waits here until it's answered, while the view keeps running
name = view.prompt("What should I call you?", placeholder="your name", title="Hello")
print(f"Hi, {name}! Pick a file and try the buttons." if name else "Fine, stay anonymous. Try the buttons.")
view.wait()
