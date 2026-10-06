import cmdgui

view = cmdgui.View("""
    label[heading]
    stdout
    text_input[input]
""")

def enter_text(text):
    view.input.value = ""
    print(text)

view.heading.text = "Console App!"
view.heading.align = "center"

view.input.on_submit(enter_text)

view.wait()