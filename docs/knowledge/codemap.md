# Codemap

## General files

| Path | What it is | When to read |
|---|---|---|
| `.claude-plugin/plugin.json` | Plugin manifest, holds the `version` | Bumping version after any functional change |
| `.claude-plugin/marketplace.json` | Single-plugin marketplace entry | Changing how the plugin is installable |
| `README.md` | User-facing overview + canonical Repository layout tree | Reference when uncertain about the full file tree |

## Dev tooling (this repo only)

| Path | What it is | When to read |
|---|---|---|
| `.claude/hooks/check-skill-completion.sh` | Stop hook — when a new `skills/*/SKILL.md` is added in a turn, verifies that the matching `commands/*.md`, `docs/knowledge/codemap.md`, and `README.md` are also touched; `exit 2` with hints if any is missing | Changing what counts as "skill is fully wired up", or debugging why the hook fires |
| `.claude/hooks/check-docs-drift.sh` | Stop hook — when a turn touches a skill/command/agent/doc/README/manifest, runs `.claude/skills/docs-drift/scripts/check_docs_drift.py`; `exit 2` with the report if it finds errors | Changing when the automatic docs-drift check fires |
| `.claude/skills/docs-drift/` | Repo-private docs-drift skill (project-level, not exported with the plugin) — deterministic checker script + semantic pass | Changing what the docs-drift check covers |
| `.claude/commands/docs-drift.md` | Project-level `/docs-drift` command that invokes the private skill | Renaming the command or editing its invocation prompt |

## Skill indexes

| Skill | Index | What it does |
|---|---|---|
| `ab-review` | [skills/ab-review-index.md](skills/ab-review-index.md) | Dual-agent pro/con review of a diff, judged by the main agent |
| `markdown-to-html-report` | [skills/markdown-to-html-report-index.md](skills/markdown-to-html-report-index.md) | Long markdown → self-contained magazine-style HTML report |
| `scope-research` | [skills/scope-research-index.md](skills/scope-research-index.md) | Surveys the codebase for a proposed change, reports per-touchpoint facts |
| `session-reflection` | [skills/session-reflection-index.md](skills/session-reflection-index.md) | Extracts session friction and proposes project rules to prevent it |
| `docs-drift` (repo-private, in `.claude/skills/`) | [skills/docs-drift-index.md](skills/docs-drift-index.md) | Verifies the plugin's docs match its code — deterministic script + semantic pass |
