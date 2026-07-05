#!/usr/bin/env bash
# Stop hook: when a new skill is added in this turn, verify that the matching
# slash command, codemap entry, and README entry were also touched. If any are
# missing, exit 2 with a message so Claude is prompted to finish the job.
#
# Triggered by .claude/settings.json on the Stop event.

set -u

log() { echo "[skill-check] $*" >&2; }

if ! command -v jq >/dev/null 2>&1; then
  log "jq not installed; skipping (install jq to enable this hook)"
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

# Claude Code transcripts are JSONL — one JSON object per line. Find the line
# number of the last user message, then look at every line after it for
# assistant tool_use blocks made during this turn.
last_user_line="$(jq -s 'map(.type == "user") | rindex(true) // -1' "$transcript_path")"
if [[ "$last_user_line" == "-1" ]]; then
  exit 0
fi

# jq's rindex is 0-based; convert to "skip the first N lines" for tail.
turn_lines="$(tail -n +$((last_user_line + 2)) "$transcript_path")"

# Extract file_paths touched by Write/Edit in this turn.
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

# Gate 1: any SKILL.md in skills/<name>/SKILL.md touched this turn?
# Private skills under .claude/skills/ are repo dev tooling, not exported with
# the plugin, so they are exempt from the catalog requirements.
skill_md_paths="$(printf '%s\n' "$touched_paths" \
  | grep -E '(^|/)skills/[^/]+/SKILL\.md$' \
  | grep -v '\.claude/skills/' || true)"

if [[ -z "$skill_md_paths" ]]; then
  exit 0
fi

# Gate 2: among the touched SKILL.md files, which are *newly added* (untracked
# or staged as add)? Use git status to classify.
if ! command -v git >/dev/null 2>&1; then
  log "git not available; skipping"
  exit 0
fi

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  exit 0
fi

new_skills=()
while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  # Normalise to repo-relative if Claude passed an absolute path.
  rel_path="${path#$PWD/}"
  status_line="$(git status --porcelain -- "$rel_path" 2>/dev/null | head -n 1)"
  [[ -z "$status_line" ]] && continue
  code="${status_line:0:2}"
  if [[ "$code" == "??" || "${code:0:1}" == "A" ]]; then
    new_skills+=("$rel_path")
  fi
done <<< "$skill_md_paths"

if [[ ${#new_skills[@]} -eq 0 ]]; then
  exit 0
fi

# Three checks against the touched files / working tree.
touched_commands=false
if printf '%s\n' "$touched_paths" | grep -qE '(^|/)commands/[^/]+\.md$'; then
  touched_commands=true
fi

diff_paths="$(git diff HEAD --name-only 2>/dev/null || true)"
touched_codemap=false
touched_readme=false
if printf '%s\n' "$diff_paths" | grep -qFx 'docs/knowledge/codemap.md'; then
  touched_codemap=true
fi
if printf '%s\n' "$diff_paths" | grep -qFx 'README.md'; then
  touched_readme=true
fi

if $touched_commands && $touched_codemap && $touched_readme; then
  exit 0
fi

# Build the feedback message for Claude.
{
  for skill_path in "${new_skills[@]}"; do
    echo "[skill-check] new skill detected: ${skill_path}"
  done
  echo
  echo "The following items have not been updated. Please add them before ending the turn:"
  echo
  if ! $touched_commands; then
    echo "- No commands/<name>.md was added"
    echo "  -> Create the matching slash command file under commands/, following the frontmatter style of the existing 4 commands."
  fi
  if ! $touched_codemap; then
    echo "- docs/knowledge/codemap.md was not updated"
    echo "  -> Add a row to the \"Skill indexes\" table pointing to skills/<name>-index.md (skip the link if no index file exists yet)."
  fi
  if ! $touched_readme; then
    echo "- README.md was not updated"
    echo "  -> Add a row to both the \"Skills in this plugin\" table and the \"Slash commands\" table."
  fi
} >&2

exit 2
