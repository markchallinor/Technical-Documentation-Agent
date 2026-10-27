#!/usr/bin/env bash
# Install the documentation agent for the current user, and optionally
# prepare one target repository.
#
# What it does, for review:
#   1. Copies the agent's rules, templates and scripts to the agent home
#      (default ~/.docs-agent).
#   2. Installs the skills into ~/.claude/skills (and ~/.copilot/skills
#      with --copilot), with the agent home path filled in.
#   3. With --target: writes the tool permissions to
#      <target>/.claude/settings.local.json and adds that file and
#      .docs-agent/ to <target>/.git/info/exclude so neither is committed.
#
# It changes nothing else in the target repository and makes no network calls.
#
# Usage:
#   scripts/install.sh [--home DIR] [--copilot]
#   scripts/install.sh --target PATH [--workspace DIR] [--home DIR] [--force]

set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENT_HOME="${HOME}/.docs-agent"
TARGET=""
WORKSPACE=""
COPILOT=0
FORCE=0

usage() { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --home) AGENT_HOME="$2"; shift 2 ;;
    --target) TARGET="$2"; shift 2 ;;
    --workspace) WORKSPACE="$2"; shift 2 ;;
    --copilot) COPILOT=1; shift ;;
    --force) FORCE=1; shift ;;
    -h|--help) usage 0 ;;
    *) echo "Unknown option: $1" >&2; usage 1 ;;
  esac
done

command -v git >/dev/null || { echo "git is required" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' \
  || { echo "Python 3.9 or later is required" >&2; exit 1; }

mkdir -p "$AGENT_HOME"
AGENT_HOME="$(cd "$AGENT_HOME" && pwd)"
VERSION="$(cat "$SOURCE_DIR/VERSION")"

# 1. Agent files
if [[ "$AGENT_HOME" != "$SOURCE_DIR" ]]; then
  for item in RULES.md VERSION extractors scripts templates config; do
    rm -rf "${AGENT_HOME:?}/$item"
    cp -R "$SOURCE_DIR/$item" "$AGENT_HOME/$item"
  done
  find "$AGENT_HOME" -name '__pycache__' -type d -prune -exec rm -rf {} +
fi
echo "Agent ${VERSION} files installed at ${AGENT_HOME}"

# 2. Skills
install_skills() {
  local dest="$1"
  for skill_dir in "$SOURCE_DIR"/skills/*/; do
    local name
    name="$(basename "$skill_dir")"
    mkdir -p "$dest/$name"
    sed "s#__AGENT_HOME__#${AGENT_HOME}#g" "$skill_dir/SKILL.md" > "$dest/$name/SKILL.md"
  done
  echo "Skills installed in ${dest}"
}
install_skills "${HOME}/.claude/skills"
[[ $COPILOT -eq 1 ]] && install_skills "${HOME}/.copilot/skills"

# 3. Target repository
if [[ -n "$TARGET" ]]; then
  [[ -d "$TARGET/.git" ]] || { echo "Not a git repository: $TARGET" >&2; exit 1; }
  TARGET="$(cd "$TARGET" && pwd)"
  SETTINGS="$TARGET/.claude/settings.local.json"
  if [[ -f "$SETTINGS" && $FORCE -ne 1 ]]; then
    echo "$SETTINGS already exists. Review it, then re-run with --force to replace it (a .bak copy is kept)." >&2
    exit 1
  fi
  mkdir -p "$TARGET/.claude"
  [[ -f "$SETTINGS" ]] && cp "$SETTINGS" "$SETTINGS.bak"

  if [[ -n "$WORKSPACE" ]]; then
    WORKSPACE="$(cd "$WORKSPACE" && pwd)"
  fi
  python3 - "$SOURCE_DIR/config/claude-settings.template.json" "$SETTINGS" "$AGENT_HOME" "$WORKSPACE" <<'PY'
import json, sys
template, out, home, workspace = sys.argv[1:5]
text = open(template, encoding="utf-8").read().replace("__AGENT_HOME__", home)
settings = json.loads(text)
if workspace:
    settings["permissions"]["allow"].insert(1, f"Read(/{workspace}/**)")
with open(out, "w", encoding="utf-8") as fh:
    json.dump(settings, fh, indent=2)
    fh.write("\n")
PY

  EXCLUDE="$TARGET/.git/info/exclude"
  mkdir -p "$(dirname "$EXCLUDE")"
  touch "$EXCLUDE"
  for pattern in ".docs-agent/" ".claude/settings.local.json" ".claude/settings.local.json.bak"; do
    grep -qxF "$pattern" "$EXCLUDE" || echo "$pattern" >> "$EXCLUDE"
  done
  echo "Tool permissions written to ${SETTINGS} (not committed)"
fi

cat <<EOF

Next steps (see docs/RUNBOOK.md):
  1. cd <repository> and create a branch, for example: git switch -c docs/baseline
  2. Start Claude Code at the repository root: claude
  3. Ask: "Use the docs-bootstrap skill to document this repository"
EOF
