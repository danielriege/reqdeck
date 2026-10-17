#!/usr/bin/env bash
# Re-record the README's media from this checkout: docs/demo.gif and docs/document.png.
#
#   scripts/record-demo.sh
#
# Installs this checkout into a throwaway virtualenv, so what is recorded is the
# code here and not whatever `reqdeck` is on your PATH. A throwaway
# XDG_CONFIG_HOME keeps your reqdeck preferences and your nvim configuration out
# of the recording. Needs vhs (https://github.com/charmbracelet/vhs) and nvim.
set -euo pipefail
cd "$(dirname "$0")/.."

for tool in vhs nvim python3; do
    command -v "$tool" >/dev/null || { echo "record-demo: needs $tool on PATH" >&2; exit 1; }
done

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

echo "Installing this checkout…"
python3 -m venv "$work/venv"
"$work/venv/bin/pip" install --quiet .
export PATH="$work/venv/bin:$PATH"

# The same look every time: the default theme, and no reload firing mid-take.
export XDG_CONFIG_HOME="$work/config"
mkdir -p "$XDG_CONFIG_HOME/reqdeck"
printf '{"theme": "dracula", "reload": 0}\n' > "$XDG_CONFIG_HOME/reqdeck/tui.json"

echo "Recording docs/document.png…"
vhs docs/document.tape
echo "Recording docs/demo.gif…"
vhs docs/demo.tape
echo "Done: docs/demo.gif, docs/document.png"
