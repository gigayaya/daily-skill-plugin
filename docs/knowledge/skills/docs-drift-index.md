# docs-drift

Checks whether the plugin's docs still match its code. A deterministic script
proves mechanical drift (catalogs, index files, links, English-only, version
bump); the skill adds the semantic pass (prose descriptions vs actual
behaviour) and proposes fixes for approval. Follows the "LLM understands /
script transforms" split. The same script backs the `check-docs-drift.sh`
Stop hook.

Repo-private: lives in `.claude/skills/` (project-level dev tooling), so it
loads only when working inside this repo and is not exported to users who
install the plugin.

| Path | What it is | When to read |
|---|---|---|
| `.claude/skills/docs-drift/SKILL.md` | Frontmatter + workflow: run the checker, do the semantic pass, propose fixes, apply on approval | Adjusting trigger conditions, the semantic checklist, or the fix flow |
| `.claude/skills/docs-drift/scripts/check_docs_drift.py` | Stdlib-only checker: catalog sync, orphan indexes, dead links, GR-1 English-only, version bump; `--json` / `--strict` / `--root`, exit 1 on errors | Adding or changing a mechanical check |
| `.claude/skills/docs-drift/README.md` | User-facing docs for the skill + CLI usage | Changing user-visible behaviour or usage |
| `.claude/commands/docs-drift.md` | Project-level slash command `/docs-drift` that invokes this skill | Renaming the command, editing its `description` / `argument-hint` / invocation prompt |
| `.claude/hooks/check-docs-drift.sh` | Stop hook that runs the checker when a turn touches catalog files | Changing when the automatic check fires |
