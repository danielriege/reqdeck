#!/usr/bin/env bash
# Set a project up for reqkit, asking as it goes.
#
#   .reqkit/init.sh            from the project root
#
# Writes .reqkit.toml, creates one unit (a CSV and its .toml) per prefix you
# name, an OPEN-QUESTIONS.md if there is none, and links the skills for Claude
# Code and Codex. Nothing is overwritten: it stops if .reqkit.toml exists.
set -euo pipefail

KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(pwd)"
REQ=(python3 "${KIT}/req.py")

die() { echo "init: $*" >&2; exit 1; }

ask() {  # ask VAR "Prompt" default
    local answer
    read -r -p "$2${3:+ [$3]}: " answer
    printf -v "$1" '%s' "${answer:-$3}"
}

yes_no() {  # yes_no "Prompt" y|n
    local answer
    read -r -p "$1 [$( [[ $2 == y ]] && echo Y/n || echo y/N )]: " answer
    answer="${answer:-$2}"
    [[ "${answer}" =~ ^[Yy] ]]
}

python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' \
    || die "reqkit needs Python 3.11 or newer (it reads TOML with the standard library)"
[[ -e "${ROOT}/.reqkit.toml" ]] && die ".reqkit.toml already exists in ${ROOT}"
[[ "${KIT}" == "${ROOT}" ]] && die "run this from the project root, not from inside reqkit"

cat <<EOF
reqkit setup in ${ROOT}

Requirements form levels, each satisfying the one above it, rooted in user
stories. Pick the shape that fits — it can be edited in .reqkit.toml later.

  1) Stories → System → Sub-system + Interface
     A product of several parts that talk to each other: firmware, hardware,
     an app. Interface requirements describe behaviour at a boundary.
  2) Stories → System → Sub-system
     Several parts, no boundary worth specifying on its own.
  3) Stories → Requirements
     One app or one component.

EOF
ask SHAPE "Shape" 1
[[ "${SHAPE}" =~ ^[123]$ ]] || die "pick 1, 2 or 3"

ask REQ_DIR "Folder for the requirement files" "docs/requirements"
ask QUESTIONS "Open questions file" "docs/OPEN-QUESTIONS.md"
ask PERSONAS "Persona letters for user stories, space-separated (A-01, B-01, …)" "A"

SYS="TSR"; SUB="TSSR"; ICD="ICD"
case "${SHAPE}" in
    1) ask SYS "System level prefix" "TSR"; ask SUB "Sub-system level prefix" "TSSR"
       ask ICD "Interface level prefix" "ICD" ;;
    2) ask SYS "System level prefix" "TSR"; ask SUB "Sub-system level prefix" "TSSR" ;;
    3) ask SYS "Requirement prefix" "REQ" ;;
esac

echo
if yes_no "Split testing into unit (U), integration (S) and manual (M) instead of one T?" n; then
    VERIFY=split
else
    VERIFY=single
fi
HEADERS=n
yes_no "C or C++ with headers — keep markers on headers, never on .c/.cpp?" n && HEADERS=y

# ------------------------------------------------------------------ the config

{
    echo "# reqkit configuration — see .reqkit/README.md."
    echo
    echo "requirements = \"${REQ_DIR}\""
    echo "questions = \"${QUESTIONS}\""
    echo
    echo "# Most abstract first. \`satisfies\` names the levels a requirement may point at."
    echo
    printf '[[levels]]\nkind = "STORY"\ntitle = "User story"\nreviewed = false\ntraced = false\nseparator = "-"\ndigits = 2\n\n'
    if [[ "${SHAPE}" == 3 ]]; then
        printf '[[levels]]\nkind = "%s"\ntitle = "Requirement"\nsatisfies = ["STORY"]\ntopic = true\n\n' "${SYS}"
    else
        printf '[[levels]]\nkind = "%s"\ntitle = "System requirement"\nsatisfies = ["STORY"]\ntopic = true\ntraced = false\n\n' "${SYS}"
        if [[ "${SHAPE}" == 1 ]]; then
            printf '[[levels]]\nkind = "%s"\ntitle = "Interface requirement"\nsatisfies = ["%s"]\n\n' "${ICD}" "${SYS}"
            printf '[[levels]]\nkind = "%s"\ntitle = "Sub-system requirement"\nsatisfies = ["%s", "%s"]\ntopic = true\n\n' "${SUB}" "${SYS}" "${ICD}"
        else
            printf '[[levels]]\nkind = "%s"\ntitle = "Sub-system requirement"\nsatisfies = ["%s"]\ntopic = true\n\n' "${SUB}" "${SYS}"
        fi
    fi
    printf '[verification.A]\nname = "Analysis"\ndefinition = "Calculation, modelling or simulation shows the requirement is met."\n\n'
    printf '[verification.I]\nname = "Inspection"\ndefinition = "Examination of the design, drawings or source, without operating it."\n\n'
    printf '[verification.D]\nname = "Demonstration"\ndefinition = "Operate the system and observe the expected behaviour."\n\n'
    if [[ "${VERIFY}" == split ]]; then
        printf '[verification.U]\nname = "Unit test"\ndefinition = "Automated, on a development machine, with the hardware mocked."\nautomated = true\n\n'
        printf '[verification.S]\nname = "Integration test"\ndefinition = "Automated, on the real target."\nautomated = true\n\n'
        printf '[verification.M]\nname = "Manual test"\ndefinition = "Measured or run by a person, with instruments where needed."\n\n'
    else
        printf '[verification.T]\nname = "Test"\ndefinition = "An automated test shows the requirement is met."\nautomated = true\n\n'
    fi
    echo "[markers]"
    if [[ "${HEADERS}" == y ]]; then
        echo 'declaration_extensions = [".h", ".hpp", ".swift", ".py"]'
        echo 'interface_suffixes = ["_interface"]'
    else
        echo "# declaration_extensions = []   # restrict non-test markers to these file types"
        echo "# interface_suffixes = []       # file stems that declare an interface, never marked"
    fi
} > "${ROOT}/.reqkit.toml"
echo "Wrote .reqkit.toml"

# ------------------------------------------------------------------- the units

export REQKIT_ROOT="${ROOT}"
mkdir -p "${ROOT}/${REQ_DIR}"

"${REQ[@]}" unit stories --level STORY --prefix "${PERSONAS}" --title "User stories" >/dev/null
echo "Created ${REQ_DIR}/stories.csv"

if [[ "${SHAPE}" == 3 ]]; then
    code=""; yes_no "Are the requirements implemented in code (so code must reference them)?" y && code="--code"
    "${REQ[@]}" unit requirements --level "${SYS}" --prefix "${SYS}" --title "Requirements" ${code} >/dev/null
    echo "Created ${REQ_DIR}/requirements.csv"
else
    "${REQ[@]}" unit system --level "${SYS}" --prefix "${SYS}" --title "System requirements" >/dev/null
    echo "Created ${REQ_DIR}/system.csv"

    add_units() {  # add_units LEVEL "what"
        local level="$1" what="$2" code_name stem title code
        echo
        echo "${what} units — one per part. Blank code to finish."
        while true; do
            ask code_name "  Unit code (e.g. FW, APP, BUS)" ""
            [[ -z "${code_name}" ]] && break
            code_name="$(tr '[:lower:]' '[:upper:]' <<< "${code_name}")"
            ask stem "  File name" "$(tr '[:upper:]' '[:lower:]' <<< "${code_name}")"
            ask title "  Title" "${code_name}"
            code=""; yes_no "  Implemented in code?" y && code="--code"
            "${REQ[@]}" unit "${stem}" --level "${level}" --prefix "${level}_${code_name}" \
                --title "${title}" ${code} >/dev/null
            echo "  Created ${REQ_DIR}/${stem}.csv — prefix ${level}_${code_name}"
        done
    }
    add_units "${SUB}" "Sub-system"
    [[ "${SHAPE}" == 1 ]] && add_units "${ICD}" "Interface"
fi

# ------------------------------------------------------- questions and skills

if [[ ! -e "${ROOT}/${QUESTIONS}" ]]; then
    mkdir -p "$(dirname "${ROOT}/${QUESTIONS}")"
    cp "${KIT}/templates/OPEN-QUESTIONS.md" "${ROOT}/${QUESTIONS}"
    echo "Created ${QUESTIONS}"
fi

echo
REL_KIT="$(python3 -c 'import os,sys; print(os.path.relpath(sys.argv[1], sys.argv[2]))' "${KIT}" "${ROOT}")"
for agent_dir in .claude/skills .agents/skills; do
    yes_no "Link the reqkit skills into ${agent_dir}?" y || continue
    mkdir -p "${ROOT}/${agent_dir}"
    for skill in "${KIT}"/skills/*/; do
        [[ -d "${skill}" ]] || continue
        name="$(basename "${skill}")"
        target="../../${REL_KIT}/skills/${name}"
        if [[ -e "${ROOT}/${agent_dir}/${name}" ]]; then
            echo "  ${agent_dir}/${name} exists — left alone"
        else
            ln -s "${target}" "${ROOT}/${agent_dir}/${name}"
            echo "  ${agent_dir}/${name} -> ${target}"
        fi
    done
done

cat <<EOF

Done. Next:
  ${REL_KIT}/req.py check        validate
  ${REL_KIT}/req.py levels       the levels and units just created
  ${REL_KIT}/tui.py              browse (needs: pip install textual)

Then write the product brief and start the first topics in ${QUESTIONS} —
the req-method skill describes how.
EOF
