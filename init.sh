#!/usr/bin/env bash
# Set a project up for reqkit, asking as it goes.
#
#   .reqkit/init.sh            from the project root
#
# Asks everything first, checks that none of the files it would create exist,
# shows a summary, and writes only once that is confirmed. A failure while
# writing removes what this run created, so a project is either set up or
# untouched. An existing OPEN-QUESTIONS.md and existing skill folders are kept.
set -Eeuo pipefail

# Physical paths throughout, so a symlink above the project (macOS's /var is
# /private/var) cannot make the kit look outside it. The kit keeps its own
# name rather than its target's, so a symlinked kit is linked as itself.
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
KIT_AS_SEEN="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)/$(basename "$(dirname "${BASH_SOURCE[0]}")")"
ROOT="$(pwd -P)"
REQ=(python3 "${KIT}/req.py")

die() { echo "init: $*" >&2; exit 1; }

# ask VAR "Prompt" default [regex] [hint] — re-asks until the answer matches.
ask() {
    local answer
    while true; do
        read -r -p "$2${3:+ [$3]}: " answer || die "input ended before setup was complete — nothing written"
        answer="${answer:-$3}"
        if [[ -z "${4:-}" || "${answer}" =~ $4 ]]; then
            printf -v "$1" '%s' "${answer}"
            return
        fi
        echo "  ${5:-not a valid answer}" >&2
    done
}

yes_no() {  # yes_no "Prompt" y|n
    local answer
    read -r -p "$1 [$( [[ $2 == y ]] && echo Y/n || echo y/N )]: " answer \
        || die "input ended before setup was complete — nothing written"
    answer="${answer:-$2}"
    [[ "${answer}" =~ ^[Yy] ]]
}

contains() {  # contains needle hay...
    local n="$1"; shift
    local x
    for x in "$@"; do [[ "${x}" == "${n}" ]] && return 0; done
    return 1
}

PREFIX_RE='^[A-Z][A-Z0-9]*$'
PREFIX_HINT="capitals and digits, starting with a letter"
PATH_RE='^[^/ ][^ ]*$'
STEM_RE='^[a-z0-9][a-z0-9-]*$'

# ---------------------------------------------------------------- preflight

python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' \
    || die "reqkit needs Python 3.11 or newer (it reads TOML with the standard library)"
[[ "${KIT}" == "${ROOT}" ]] && die "run this from the project root, not from inside reqkit"
if [[ -e "${ROOT}/.reqkit.toml" ]]; then
    die ".reqkit.toml already exists — this project is set up. Add a unit with
  ${KIT}/req.py unit <file> --level <LEVEL> --prefix <PREFIX> --title <title>"
fi

# ---------------------------------------------------------------- questions

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
ask SHAPE "Shape" 1 '^[123]$' "pick 1, 2 or 3"
ask REQ_DIR "Folder for the requirement files" "docs/requirements" "${PATH_RE}" \
    "a relative path without spaces"
ask QUESTIONS "Open questions file" "docs/OPEN-QUESTIONS.md" "${PATH_RE}" \
    "a relative path without spaces"
while true; do
    ask PERSONAS "Persona letters for user stories, space-separated (A-01, B-01, …)" "A" \
        '^[A-Z]( [A-Z])*$' "single capital letters separated by spaces, e.g. A B C"
    read -r -a LETTERS <<< "${PERSONAS}"
    (( $(printf '%s\n' "${LETTERS[@]}" | sort -u | wc -l) == ${#LETTERS[@]} )) && break
    echo "  each letter once" >&2
done

SYS="TSR"; SUB="TSSR"; ICD="ICD"
while true; do
    if [[ "${SHAPE}" == 3 ]]; then
        ask SYS "Requirement prefix" "REQ" "${PREFIX_RE}" "${PREFIX_HINT}"
    else
        ask SYS "System level prefix" "TSR" "${PREFIX_RE}" "${PREFIX_HINT}"
    fi
    ! contains "${SYS}" "${LETTERS[@]}" && break
    echo "  ${SYS} is a persona letter" >&2
done
if [[ "${SHAPE}" != 3 ]]; then
    while true; do
        ask SUB "Sub-system level prefix" "TSSR" "${PREFIX_RE}" "${PREFIX_HINT}"
        ! contains "${SUB}" "${SYS}" "${LETTERS[@]}" && break
        echo "  must differ from ${SYS} and the persona letters" >&2
    done
fi
if [[ "${SHAPE}" == 1 ]]; then
    while true; do
        ask ICD "Interface level prefix" "ICD" "${PREFIX_RE}" "${PREFIX_HINT}"
        ! contains "${ICD}" "${SYS}" "${SUB}" "${LETTERS[@]}" && break
        echo "  must differ from ${SYS}, ${SUB} and the persona letters" >&2
    done
fi

echo
VERIFY=single
yes_no "Split testing into unit (U), integration (S) and manual (M) instead of one T?" n && VERIFY=split
HEADERS=n
yes_no "C or C++ with headers — keep markers on headers, never on .c/.cpp?" n && HEADERS=y

# Units: parallel arrays of file stem, level, prefix, title, code flag.
U_STEM=(stories); U_LEVEL=(STORY); U_PREFIX=("${PERSONAS}"); U_TITLE=("User stories"); U_CODE=(n)

if [[ "${SHAPE}" == 3 ]]; then
    code=n; yes_no "Are the requirements implemented in code (so code must reference them)?" y && code=y
    U_STEM+=(requirements); U_LEVEL+=("${SYS}"); U_PREFIX+=("${SYS}"); U_TITLE+=("Requirements"); U_CODE+=("${code}")
else
    U_STEM+=(system); U_LEVEL+=("${SYS}"); U_PREFIX+=("${SYS}"); U_TITLE+=("System requirements"); U_CODE+=(n)

    ask_units() {  # ask_units LEVEL "what"
        local level="$1" code_name stem title code
        echo
        echo "$2 units — one per part. Blank code to finish."
        while true; do
            ask code_name "  Unit code (e.g. FW, APP, BUS)" "" '^([A-Za-z][A-Za-z0-9]*)?$' \
                "letters and digits, starting with a letter"
            [[ -z "${code_name}" ]] && break
            code_name="$(tr '[:lower:]' '[:upper:]' <<< "${code_name}")"
            if contains "${level}_${code_name}" "${U_PREFIX[@]}"; then
                echo "  ${level}_${code_name} is already a unit" >&2
                continue
            fi
            while true; do
                ask stem "  File name" "$(tr '[:upper:]' '[:lower:]' <<< "${code_name}")" "${STEM_RE}" \
                    "lower case letters, digits and hyphens"
                ! contains "${stem}" "${U_STEM[@]}" && break
                echo "  ${stem} is already taken" >&2
            done
            ask title "  Title" "${code_name}"
            code=n; yes_no "  Implemented in code?" y && code=y
            U_STEM+=("${stem}"); U_LEVEL+=("${level}"); U_PREFIX+=("${level}_${code_name}")
            U_TITLE+=("${title}"); U_CODE+=("${code}")
        done
    }
    ask_units "${SUB}" "Sub-system"
    [[ "${SHAPE}" == 1 ]] && ask_units "${ICD}" "Interface"
fi

LINK_DIRS=()
for agent_dir in .claude/skills .agents/skills; do
    yes_no "Link the reqkit skills into ${agent_dir}?" y && LINK_DIRS+=("${agent_dir}")
done

# ---------------------------------------------------------------- conflicts

conflicts=()
for stem in "${U_STEM[@]}"; do
    for ext in csv toml details.md; do
        [[ -e "${ROOT}/${REQ_DIR}/${stem}.${ext}" ]] && conflicts+=("${REQ_DIR}/${stem}.${ext}")
    done
done
if (( ${#conflicts[@]} )); then
    printf '  %s\n' "${conflicts[@]}" >&2
    die "these files already exist — move them away or pick other names; nothing written"
fi

KEEP_QUESTIONS=n
if [[ -e "${ROOT}/${QUESTIONS}" ]]; then
    KEEP_QUESTIONS=y
    grep -qE '^## Topic [0-9]{2} — ' "${ROOT}/${QUESTIONS}" || echo "warning: ${QUESTIONS} exists but has no
  '## Topic NN — Title' heading, so reqkit will find no topics in it. It is kept as it is." >&2
fi

# ---------------------------------------------------------------- summary

echo
echo "About to create:"
echo "  .reqkit.toml"
for i in "${!U_STEM[@]}"; do
    printf '  %-36s %-12s %s%s\n' "${REQ_DIR}/${U_STEM[$i]}.csv" "${U_PREFIX[$i]}" "${U_TITLE[$i]}" \
        "$( [[ ${U_CODE[$i]} == y ]] && echo ' (code)')"
done
[[ "${KEEP_QUESTIONS}" == n ]] && echo "  ${QUESTIONS}"
for d in "${LINK_DIRS[@]+"${LINK_DIRS[@]}"}"; do echo "  ${d}/ links to the reqkit skills"; done
echo
yes_no "Create these?" y || die "nothing written"

# ---------------------------------------------------------------- writing

CREATED=()
rollback() {
    local p i
    trap - ERR
    echo "init: setup failed — removing what this run created" >&2
    for (( i=${#CREATED[@]}-1; i>=0; i-- )); do
        p="${CREATED[$i]}"
        if [[ -L "${p}" || -f "${p}" ]]; then rm -f "${p}"; elif [[ -d "${p}" ]]; then rmdir "${p}" 2>/dev/null || true; fi
    done
}
trap 'rollback' ERR
trap 'rollback; exit 130' INT TERM

mkdir_tracked() {  # mkdir_tracked DIR — creates parents, remembering each new one
    local d="$1" missing=()
    while [[ ! -e "${d}" ]]; do missing=("${d}" "${missing[@]+"${missing[@]}"}"); d="$(dirname "${d}")"; done
    for d in "${missing[@]+"${missing[@]}"}"; do mkdir "${d}"; CREATED+=("${d}"); done
}

CREATED+=("${ROOT}/.reqkit.toml")
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

export REQKIT_ROOT="${ROOT}"
mkdir_tracked "${ROOT}/${REQ_DIR}"
for i in "${!U_STEM[@]}"; do
    CREATED+=("${ROOT}/${REQ_DIR}/${U_STEM[$i]}.csv" "${ROOT}/${REQ_DIR}/${U_STEM[$i]}.toml")
    code=(); [[ "${U_CODE[$i]}" == y ]] && code=(--code)
    "${REQ[@]}" unit "${U_STEM[$i]}" --level "${U_LEVEL[$i]}" --prefix "${U_PREFIX[$i]}" \
        --title "${U_TITLE[$i]}" "${code[@]+"${code[@]}"}" >/dev/null
done

if [[ "${KEEP_QUESTIONS}" == n ]]; then
    mkdir_tracked "$(dirname "${ROOT}/${QUESTIONS}")"
    CREATED+=("${ROOT}/${QUESTIONS}")
    cp "${KIT}/templates/OPEN-QUESTIONS.md" "${ROOT}/${QUESTIONS}"
fi

REL_KIT="$(python3 -c 'import os,sys; print(os.path.relpath(sys.argv[1], sys.argv[2]))' "${KIT_AS_SEEN}" "${ROOT}")"
SKIPPED=()
for agent_dir in "${LINK_DIRS[@]+"${LINK_DIRS[@]}"}"; do
    mkdir_tracked "${ROOT}/${agent_dir}"
    for skill in "${KIT}"/skills/*/; do
        [[ -d "${skill}" ]] || continue
        name="$(basename "${skill}")"
        if [[ -e "${ROOT}/${agent_dir}/${name}" || -L "${ROOT}/${agent_dir}/${name}" ]]; then
            SKIPPED+=("${agent_dir}/${name}")
        else
            CREATED+=("${ROOT}/${agent_dir}/${name}")
            ln -s "../../${REL_KIT}/skills/${name}" "${ROOT}/${agent_dir}/${name}"
        fi
    done
done

"${REQ[@]}" check >/dev/null
trap - ERR INT TERM

for s in "${SKIPPED[@]+"${SKIPPED[@]}"}"; do echo "kept the existing ${s} — it is not reqkit's link"; done
cat <<EOF
Done. Next:
  ${REL_KIT}/req.py check        validate
  ${REL_KIT}/req.py levels       the levels and units just created
  ${REL_KIT}/tui.py              browse (needs: pip install textual)

Then write the product brief and start the first topics in ${QUESTIONS} —
the req-method skill describes how.
EOF
