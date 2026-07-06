# docs-drift

A **docs-drift** skill for this repo. It lives in `.claude/skills/`
(project-level dev tooling), so it loads only when working inside this repo
and is **not exported** to users who install the plugin. The docs in this
repo are
hand-maintained — the README "Skills in this plugin" and "Slash commands"
tables, the codemap "Skill indexes" table, the per-skill
`docs/knowledge/skills/<name>-index.md` files, and a pile of relative links.
Every time a skill or command is added, renamed, or removed, one of those can
fall out of sync. This skill checks that they haven't.

It follows the repo's **"LLM understands / script transforms"** split:

- A standalone Python script (`scripts/check_docs_drift.py`) does the
  deterministic half — it reads the ground truth off disk and reports every
  **mechanical** mismatch it can prove.
- The skill (Claude) does the **semantic** half — comparing each doc's prose
  against what the code actually does, which a script cannot judge.

Triggered manually when you ask Claude to check docs drift, or via
`/docs-drift`. The same script also backs a Stop hook
(`.claude/hooks/check-docs-drift.sh`), so mechanical drift is caught
automatically whenever a turn ends with uncommitted changes to catalog files
(detected via `git status`).

## What the script checks (mechanical, deterministic)

| Category | Drift it catches | Severity |
|---|---|---|
| `skill-catalog` | A skill in `skills/` missing its index file, its README row, or its codemap row; frontmatter `name` ≠ directory name | error (name = warning) |
| `command-catalog` | A `commands/<slug>.md` not listed in the README "Slash commands" table | error |
| `skill-command` | An exported skill that no `commands/*.md` mentions (every skill ships a slash command; slugs may differ from skill names) | error |
| `orphan` | An index file pointing at a skill that no longer exists | error |
| `dead-link` | A relative markdown link whose target file is gone (placeholders with `<…>` are skipped) | error |
| `english-only` | A file containing CJK/Kana/Hangul (GR-1) | warning |
| `manifest-sync` | `plugin.json` `description` differing from the plugin's entry in `marketplace.json` | error |
| `version-bump` | Functional files changed vs `HEAD` with no `plugin.json` version bump | warning |

`errors` mean the docs are provably out of sync. `warnings` may have a
legitimate exception (e.g. a quoted non-English source), so Claude judges each.

## What Claude adds (semantic, on top of the script)

- README / codemap / index **one-line descriptions** vs what each `SKILL.md`
  actually does.
- **Dependency claims** in the docs vs the real `scripts/requirements.txt`.
- README **"Repository layout"** tree and
  `docs/knowledge/architecture.md` vs the real tree and the real skills.
- Then it **proposes fixes** and edits docs **only after you approve**.

## Running the script directly

```bash
python .claude/skills/docs-drift/scripts/check_docs_drift.py          # human-readable
python .claude/skills/docs-drift/scripts/check_docs_drift.py --json   # machine output
python .claude/skills/docs-drift/scripts/check_docs_drift.py --strict # warnings fail too (CI)
python .claude/skills/docs-drift/scripts/check_docs_drift.py --root . # point at a checkout
```

Exit code `0` = no errors, `1` = errors found (or warnings under `--strict`).

## Required dependencies

**None.** The script is standard-library Python only — no `pip install` step.

## File layout

```
docs-drift/
├── SKILL.md                      # skill description + workflow
├── README.md                     # this file
└── scripts/
    └── check_docs_drift.py       # stdlib-only mechanical drift checker (CLI)
```

## Notes

- Manual-trigger only — Claude never auto-invokes the skill (the Stop hook
  runs the script automatically, but never edits anything).
- Fix the **doc** to match the code by default; only touch code if you confirm
  the code is what drifted.
- Read-first, write-on-approval: the analysis stays in chat; only approved
  edits are persisted.
