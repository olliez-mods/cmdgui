from pathlib import Path
from cmdgui import View, Menu, Text, KeyHints

# A reader for this project's own docs. Pick a page on the left; Text(markdown=True) shows
# it. Scroll with the wheel, or click the page (or Tab to it) and use the arrow keys and
# Page Up/Down. Click a link: other pages open here, web links open in your browser.

ROOT = Path(__file__).resolve().parent.parent
PAGES = [ROOT / "README.md"] + sorted((ROOT / "docs").glob("*.md"))

def show(index, path):
    view.page.set(text=path.read_text(), scroll=0, title=path.name)

def follow(url):
    """A link was clicked: another page of the docs opens here (at the heading after #, if
    there is one), anything else in the browser. Links to a heading on the same page
    (#install) are handled by Text itself."""
    target, _, anchor = url.partition("#")
    page = next((p for p in PAGES if target and p.name == Path(target).name), None)
    if page is not None:
        view.pages.selected = PAGES.index(page)
        show(view.pages.selected, page)
        if anchor: view.page.scroll_to(anchor)
    else:
        import webbrowser
        webbrowser.open(url)
        view.notify(f"Opened {url}", "info")

class App(View):
    layout = """
        pages{+b}  page{+b}
        hints      -
    """
    pages = Menu([p.name for p in PAGES], title="pages", on_select=lambda i, name: show(i, PAGES[i]))
    page = Text(markdown=True, on_link=follow)
    hints = KeyHints()

view = App()
view.adjustable(view.pages, view.page, position=22)
show(0, PAGES[0])
view.focus(view.pages)
view.wait()
