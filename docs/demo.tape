# The README's demo. Recorded by scripts/record-demo.sh, which installs this
# checkout and sets a clean XDG_CONFIG_HOME first — run that, not this tape alone.

Output docs/demo.gif

Set Shell "bash"
Set FontSize 15
Set Width 1440
Set Height 840
Set Padding 16
Set Theme "Dracula"
Set TypingSpeed 60ms
Set WindowBar Colorful

Hide
Type "export PS1='$ ' && cd examples/tick && clear" Enter
Show

Type "reqdeck tui" Sleep 400ms Enter
Sleep 2s

# Down the tree to the app's requirements, shown as a document.
Type "jjjj" Sleep 600ms
Type "l" Sleep 400ms
Type "j" Sleep 400ms
Type "l" Sleep 2.5s

# Into the reminders section, onto one requirement.
Type "jjj" Sleep 500ms
Type "l" Sleep 400ms
Type "jj" Sleep 2.5s

# Its links: the question it came from, what it satisfies, the code behind it.
Tab Sleep 2s
Tab Sleep 2s
Tab Sleep 3s

# Open the code in the editor, at the marker.
Enter Sleep 3s
Type ":q" Sleep 300ms Enter
Sleep 1.5s

# Follow a link, and come back.
Shift+Tab Sleep 1.5s
Enter Sleep 2.5s
Ctrl+O Sleep 2s

# Search.
Type "/" Sleep 400ms
Type "sync" Sleep 1s Enter
Sleep 2s
Type "n" Sleep 1.5s
Escape Sleep 1s

# Reload from disk — it also does so on its own, every 30 seconds.
Type "r" Sleep 2s

# Themes, previewed as the cursor moves.
Type "t" Sleep 1s
Type "j" Sleep 1.2s
Type "j" Sleep 1.2s
Type "j" Sleep 1.2s
Escape Sleep 1s

Type "q"
Sleep 500ms
