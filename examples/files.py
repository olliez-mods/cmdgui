from cmdgui import View, Tree, Text
from cmdgui.shorts import escape
import os

# A file browser: folders load their contents when you first open them.
# Arrows to move (right opens, left closes), Enter or click to pick, q to quit.
# Drag the line between the files and the preview to resize them.

def folder(path):
    def load():
        try:
            names = sorted(os.listdir(path), key=lambda n: (not os.path.isdir(os.path.join(path, n)), n.lower()))
        except OSError as e:
            return [f"({e.strerror})"]
        return {name: folder(os.path.join(path, name)) if os.path.isdir(os.path.join(path, name)) else None
                for name in names}
    return load

root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def show(path):
    full = os.path.join(root, *path)
    if os.path.isdir(full):
        # escape(): a path with [ in it would otherwise be read as markup
        view.preview.set(text=f"[bold]{escape(full)}[/]\n\n[cyan]{len(os.listdir(full))}[/] items", markup=True)
        return
    try:
        with open(full, encoding="utf-8") as f:
            view.preview.set(text=f.read(4000), markup=False)  # a file's text, shown exactly as it is
    except (OSError, UnicodeDecodeError) as e:
        view.preview.set(text=f"[red]Can't show this file:[/] {escape(str(e))}", markup=True)

class App(View):
    layout = "files{+b} preview{+b}"
    files = Tree(folder(root), title=os.path.basename(root), on_select=show)
    preview = Text("Pick a file")

view = App()
view.adjustable(view.files, view.preview, position=0.3)  # the files get 30% of the width; dragging keeps it a fraction
view.focus(view.files)
view.wait()
