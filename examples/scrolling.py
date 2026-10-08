from cmdgui import View, Panel, Label, TextInput, TextArea, Checkbox, Toggle, Slider, Menu, Stdout, KeyHints

# A form taller than the screen, in a panel that scrolls: {+s} in the layout (or
# Panel(scrollable=True)). Scroll it with the wheel, or Tab through it and it follows the
# focus. Over the colour list the wheel scrolls the list instead, since it scrolls itself.
# The bar on the right edge shows where you are. q quits when not typing.

class LongForm(Panel):
    layout = """
        intro    -
        first    last
        email    phone
        street   -
        city     postcode
        colour   -
        size     -
        news     updates
        notes    -
        outro    -
    """
    intro = Label("[dim]Scroll down, or press Tab to go through the boxes.[/]")
    first = TextInput(title="first name", border=True)
    last = TextInput(title="last name", border=True)
    email = TextInput(title="email", placeholder="you@example.com", border=True)
    phone = TextInput(title="phone", border=True)
    street = TextInput(title="street", border=True)
    city = TextInput(title="city", border=True)
    postcode = TextInput(title="postcode", border=True)
    colour = Menu(["red", "orange", "yellow", "green", "blue", "indigo", "violet", "black", "white"],
                  title="favourite colour (the wheel scrolls this list)", preferred_height=4)
    size = Slider(5, min=1, max=10, step=1, title="how much you like forms", border=True)
    news = Checkbox("send me news")
    updates = Toggle("weekly updates")
    notes = TextArea(title="notes", placeholder="anything else", border=True, preferred_height=4)
    outro = Label("[dim]That's the end of the form.[/]")

class App(View):
    layout = """
        form{+b,+s}  log{+b}
        hints        -
    """
    form = LongForm(title="a long form")
    log = Stdout()
    hints = KeyHints()

view = App()
view.adjustable(view.form, view.log, position=0.6)
view.form.on_values_change(lambda values: print({k: v for k, v in values.items() if v not in ("", False)}))
print("Edits show up here.")
view.wait()
