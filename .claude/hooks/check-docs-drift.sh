#!/usr/bin/env bash
# Stop hook: when the working tree has uncommitted changes (staged, unstaged,
# or untracked) under any path the docs describe — a skill, a command, an
# agent, a doc, the README, or the plugin manifests — run the deterministic
# docs-drift checker. If it finds errors, exit 2 with the report so Claude
# fixes the drift before ending the turn. Warnings do not block.
#
# Changed files are detected via `git status`, not by parsing the session
# transcript: in transcripts, tool results are `type: "user"` lines, so a
# "since the last user message" window never contains the turn's Write/Edit
# calls — and transcript parsing misses files changed through Bash anyway.
# Git sees them all.
#
# This is the mechanical half of the docs-drift skill, wired to run
# automatically. The semantic half (prose vs behaviour) is the skill's job.
#
# Triggered by .claude/settings.json on the Stop event. Dev tooling for this
# repo only.

set -u

log() { echo "[docs-drift] $*" >&2; }

payload="$(cat)"

# One blocking round per turn: if this Stop already follows a Stop-hook
# block, let the turn end so an unfixable finding cannot loop forever.
if printf '%s' "$payload" | grep -Eq '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
  exit 0
fi

if ! command -v python3 >/dev/null 2>&1; then
  log "python3 not available; skipping"
  exit 0
fi
if ! command -v git >/dev/null 2>&1; then
  log "git not available; skipping"
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$PWD}" || { log "cannot cd to project dir; skipping"; exit 0; }

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  exit 0
fi

script=".claude/skills/docs-drift/scripts/check_docs_drift.py"
if [[ ! -f "$script" ]]; then
  log "checker not found at $script; skipping"
  exit 0
fi

# Only run the checker when a doc-relevant path has uncommitted changes.
if ! git status --porcelain | grep -qE \
  '(^|/| )(skills/|commands/|agents/|docs/|README\.md|\.claude-plugin/)'; then
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
