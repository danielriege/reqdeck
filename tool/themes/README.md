# Themes

One file per theme, named after the [Textual theme](https://textual.textualize.io/guide/design/)
it extends. Textual supplies the base colours; the file adds every colour reqkit draws
with, taken from that theme's own palette, in the roles below. Nothing paints a
background — the terminal's own shows through — so a role is a text or border colour,
except `selection`, the one filled row.

| Role | Draws |
|---|---|
| `foreground` | Ordinary text |
| `muted` | Field labels, rationale, guides, the key hint line |
| `border` | Every panel border |
| `border_active` | The focused panel's border |
| `border_search` | The tree's border while a search filters it |
| `selection` | The cursor row in the focused panel |
| `title` | Panel titles, the unit and level names in the tree |
| `heading` | Section headings and numbers in a document |
| `id` | A requirement or question ID |
| `link` | An ID in running text, which can be followed |
| `link_active` | The link under the keyboard cursor, and the preview's border |
| `code` | Inline code — byte values, command codes |
| `table_header` | A table's header row |
| `statement_bar` | The bar beside a requirement's statement |
| `accepted` `proposed` `reopened` | Review status |
| `security` | The security-relevant marker |
| `open` `answered` | An open question's state |
| `keys` | Key names in the hint line |

A theme in `~/.config/reqkit/themes/` is loaded as well, and replaces a bundled one of the
same name. Its `extends` names the Textual theme to start from.
