from cmdgui import View, Tree, Text
import os

# A file browser: folders load their contents when you first open them.
# Arrows to move (right opens, left closes), Enter or click to pick, q to quit

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
        view.preview.text = f"{full}\n\n{len(os.listdir(full))} items"
        return
    try:
        with open(full, encoding="utf-8") as f:
            view.preview.text = f.read(4000)
    except (OSError, UnicodeDecodeError) as e:
        view.preview.text = f"Can't show this file: {e}"

class Browser(View):
    layout = "files  preview  -"
    files = Tree(folder(root), title=os.path.basename(root), on_select=show)
    preview = Text("Pick a file", border=True)

view = Browser()
view.focus(view.files)
view.wait()
