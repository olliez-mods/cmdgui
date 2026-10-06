# Themes and colors

## Themes

A theme is a dict of style names to styles. Pass the ones you want to change:

```python
from cmdgui import View, style

view = View("...", theme={
    "border_focus": style(fg="magenta", bold=True),
    "selected": style(fg="black", bg="yellow"),
})
```

| Key | Used for | Default |
|---|---|---|
| `border` | borders | plain |
| `border_focus` | the focused widget's border | cyan, bold |
| `title` | border titles | bold |
| `text` | `Text` and `Label` | plain |
| `dim` | placeholders, hints | bright black |
| `error` | stderr in `Stdout`, error messages in `Log` | red |
| `button` | buttons | plain |
| `button_hover` | a button or select under the mouse | reversed |
| `button_focus` | a focused button, select, checkbox or radio option | cyan, bold |
| `cursor` | the cursor in text boxes | reversed |
| `selected` | the selected item in a focused menu or tree, the chosen day in a calendar | black on cyan |
| `selected_unfocused` | the same, when not focused | reversed |
| `hover` | the menu item or tab under the mouse | on bright black |
| `progress`, `progress_empty` | the two parts of a progress bar | green, bright black |
| `slider`, `slider_empty` | the two parts of a slider | cyan, bright black |
| `slider_focus` | the slider's handle while focused or dragged | cyan, bold, reversed |
| `header` | table headers | bold, underlined |
| `tab` | a tab on a `Tabs` bar | plain |
| `tab_active` | the shown tab's name (on a borderless `Tabs` with the bar focused, `selected` is used) | bold |
| `on`, `off` | a toggle's switch | black on green, reversed bright black |
| `divider_hover` | a `Split`'s divider under the mouse, or being dragged | bold yellow |
| `today` | today's date in a `Calendar` | bold, underlined |
| `log_debug`, `log_info`, `log_warning`, `log_error`, `log_critical` | the level names in a `Log` | bright black, cyan, bold yellow, bold red, bold white on red |
| `match` | text matching a `Log`'s search | black on yellow |
| `disabled` | replaces every style in a disabled widget | bright black |

The defaults are in `DEFAULT_THEME`. Your own widgets can add keys and read them with
`self.theme("key")`, see [Your own widgets](custom-widgets.md).

## Styles

`style()` makes a style:

```python
style(fg="orange", bg="navy", bold=True, dim=False, italic=False, underline=False, reverse=False)
```

`styled(text, ...)` wraps text in a style for printing straight to the terminal:
`print(styled("done", fg="green", bold=True))`.

## Colors

Colors for `fg` and `bg` can be:

- **a basic color**, which follows the terminal's own theme: `black`, `red`, `green`,
  `yellow`, `blue`, `magenta`, `cyan`, `white`, each also as `bright_red` and so on.
- **a named color** from the 256-color palette, which nearly every terminal supports
  (listed below).
- **a 256-color palette number**: `style(fg=208)`.
- **an exact color**: `style(fg="#ff8800")` or `style(fg=(255, 136, 0))`. These need a
  terminal with true color: Windows Terminal, VS Code and iTerm2 have it, macOS's
  Terminal.app doesn't.

Names are case-insensitive, spaces work like underscores, and `grey` works wherever
`gray` does: `"Dark Grey"` is `"dark_gray"`. Your editor autocompletes the names, and
an unknown one raises a `ValueError`.

| Group | Names |
|---|---|
| Reds and pinks | `dark_red`, `maroon`, `crimson`, `scarlet`, `coral`, `salmon`, `rose`, `pink`, `hot_pink`, `deep_pink` |
| Oranges, yellows and browns | `orange`, `dark_orange`, `amber`, `gold`, `lemon`, `cream`, `peach`, `tan`, `khaki`, `brown`, `rust`, `copper` |
| Greens | `lime`, `chartreuse`, `olive`, `dark_green`, `forest`, `emerald`, `sea_green`, `mint`, `pale_green` |
| Blues and cyans | `teal`, `turquoise`, `aqua`, `sky`, `light_blue`, `steel_blue`, `cornflower`, `royal_blue`, `dodger_blue`, `dark_blue`, `navy`, `slate` |
| Purples | `indigo`, `purple`, `dark_purple`, `violet`, `lavender`, `plum`, `orchid`, `fuchsia` |
| Grays | `charcoal`, `dark_gray`, `gray`, `silver`, `light_gray`, `snow` |

The palette numbers are in `EXTRA_COLORS` in `cmdgui.shorts`. For type hints in your
own code, use `Color` (any color) or `ColorName` (just the names), both from `cmdgui`.
