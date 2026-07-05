#!/usr/bin/env bash
# Stop hook: when this turn touched any file that the docs describe (a skill, a
# command, an agent, a doc, the README, or the plugin manifest), run the
# deterministic docs-drift checker. If it finds errors, exit 2 with the report
# so Claude fixes the drift before ending the turn. Warnings do not block.
#
# This is the mechanical half of the docs-drift skill, wired to run
# automatically. The semantic half (prose vs behaviour) is the skill's job.
#
# Triggered by .claude/settings.json on the Stop event. Dev tooling for this
# repo only.

set -u

log() { echo "[docs-drift] $*" >&2; }

if ! command -v jq >/dev/null 2>&1; then
  log "jq not installed; skipping (install jq to enable this hook)"
  exit 0
fi
if ! command -v python3 >/dev/null 2>&1; then
  log "python3 not available; skipping"
  exit 0
fi

payload="$(cat)"
transcript_path="$(printf '%s' "$payload" | jq -r '.transcript_path // empty')"
project_dir="$(printf '%s' "$payload" | jq -r '.cwd // empty')"

if [[ -z "$transcript_path" || ! -f "$transcript_path" ]]; then
  log "no transcript_path in payload; skipping"
  exit 0
fi

if [[ -n "$project_dir" && -d "$project_dir" ]]; then
  cd "$project_dir" || { log "cannot cd to $project_dir; skipping"; exit 0; }
fi

script="${CLAUDE_PROJECT_DIR:-$PWD}/.claude/skills/docs-drift/scripts/check_docs_drift.py"
if [[ ! -f "$script" ]]; then
  log "checker not found at $script; skipping"
  exit 0
fi

# Find the line of the last user message; only inspect this turn's tool calls.
last_user_line="$(jq -s 'map(.type == "user") | rindex(true) // -1' "$transcript_path")"
if [[ "$last_user_line" == "-1" ]]; then
  exit 0
fi
turn_lines="$(tail -n +$((last_user_line + 2)) "$transcript_path")"

# Files written/edited this turn.
touched_paths="$(printf '%s' "$turn_lines" \
  | jq -r 'select(.type == "assistant")
      | .message.content[]?
      | select(.type == "tool_use")
      | select(.name == "Write" or .name == "Edit")
      | .input.file_path // empty' \
  2>/dev/null)"

if [[ -z "$touched_paths" ]]; then
  exit 0
fi

# Only run the checker if a doc-relevant file was touched this turn.
if ! printf '%s\n' "$touched_paths" | grep -qE \
  '(^|/)(skills/|commands/|agents/|docs/|README\.md|\.claude-plugin/)'; then
  exit 0
fi

report="$(python3 "$script" 2>&1)"
status=$?

if [[ "$status" -ne 0 ]]; then
  {
    echo "Docs drift detected. Fix these before ending the turn:"
    echo
    echo "$report"
  } >&2
  exit 2
fi

exit 0
