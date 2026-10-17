# The README's screenshot: a unit shown as a document, with numbered sections and
# a detail table. Recorded by scripts/record-demo.sh — run that, not this tape alone.

# vhs records a video whatever else it does; this one is thrown away.
Output "/tmp/reqdeck-document.gif"

Set Shell "bash"
Set FontSize 15
Set Width 1440
Set Height 840
Set Padding 16
Set Theme "Dracula"
Set WindowBar Colorful

Hide
Type "export PS1='$ ' && cd examples/tick && clear" Enter
Type "reqdeck tui" Enter
Sleep 2s
# Down to the interface level, open it, onto its one unit.
Type "jjj" Sleep 300ms
Type "l" Sleep 300ms
Type "j" Sleep 2s
Show
Sleep 500ms
Screenshot docs/document.png
Sleep 200ms
Hide
Type "q"
