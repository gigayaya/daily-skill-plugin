# Architecture

Every skill follows an **"LLM understands / script transforms"** split: the
LLM reads `SKILL.md` and produces structured intermediate data; a standalone
Python script does the deterministic transformation; a documented data format
is the contract between them. This keeps scripts small, unit-testable, and
runnable as plain CLIs without Claude.

"Understands" can include *re-authoring*, not just classifying. In
`markdown-to-html-report`, for example, the LLM rewrites each source section
into distilled prose (`body_markdown` in the metadata contract) and the script
only renders it — the editorial judgment lives on the LLM side, the
deterministic HTML/sanitization work on the script side.

Skills are auto-discovered from `skills/<name>/SKILL.md` — the YAML
`description` field is what triggers invocation. Bundled assets are referenced
via `${CLAUDE_PLUGIN_ROOT}` so paths survive installation.

Repo-private skills (dev tooling for this repo, e.g. `docs-drift`) live in
`.claude/skills/<name>/` instead: they load as project-level skills only when
working inside this repo and are not exported to plugin installers. They
reference assets via `${CLAUDE_PROJECT_DIR}` and are exempt from the README
skill/command catalogs.
