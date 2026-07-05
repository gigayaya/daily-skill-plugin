---
name: docs-drift
description: Use when the user wants to verify this plugin's docs are still in sync with its code after a change — e.g. "check for docs drift", "did the README drift", "are the docs still accurate", "I updated the plugin, verify the docs", "/docs-drift". Runs a deterministic checker for mechanical drift (skill/command catalogs in README and codemap, per-skill index files, dead relative links, English-only rule, version bump) and then does a semantic pass the script cannot — comparing each doc's prose description against what the skill actually does and the dependencies it actually ships. Proposes concrete fixes and only edits docs after the user approves. Manual-trigger only — never auto-invoke; never edit files without approval.
---

# Docs Drift

When invoked, check whether this plugin's **documentation still matches its
code**, then propose fixes. "Drift" is anything a doc claims that the repo no
longer backs up: a skill missing from a catalog table, a dead link, a README
sentence that describes behaviour the skill no longer has, a dependency list
that no longer matches `requirements.txt`.

Two layers, in order: a deterministic **script** that proves mechanical drift,
then a **semantic pass** that only an LLM can do. Report both, fix on approval.

## When to invoke

- **Manual only.** The user asks to check docs drift / doc accuracy, or runs
  `/docs-drift`. Typically right after adding, renaming, or removing a skill,
  command, or agent.
- **Never auto-invoke**, and **never edit any file before the user approves.**

## Workflow

### Step 1 — Run the mechanical checker

It is standard-library Python — no install needed.

```bash
python ${CLAUDE_PROJECT_DIR}/.claude/skills/docs-drift/scripts/check_docs_drift.py --json
```

The script resolves the repo root via `git` (or `--root DIR`) and reports, as
JSON, every mismatch it can prove:

- **skill-catalog** — a skill in `skills/` missing its
  `docs/knowledge/skills/<name>-index.md`, its README "Skills in this plugin"
  row, or its codemap "Skill indexes" row; frontmatter `name` not matching the
  directory.
- **command-catalog** — a `commands/<slug>.md` not listed in the README
  "Slash commands" table.
- **orphan** — an index file pointing at a skill that no longer exists.
- **dead-link** — a relative markdown link whose target file is gone.
- **english-only** — a file containing CJK/Kana/Hangul (GR-1); a *warning*,
  since a quoted non-English source is allowed.
- **version-bump** — functional files changed vs `HEAD` without a
  `plugin.json` version bump; a *warning*.

`errors` block a clean bill of health; `warnings` may have legitimate
exceptions (judge each). Use the human-readable form (drop `--json`) if you
just want to read it.

### Step 2 — Semantic pass (what the script cannot check)

The script proves *structural* facts; it cannot read meaning. Do this part
yourself. For **each skill**, open its `SKILL.md` and compare against:

- its **one-line description** in the README "Skills in this plugin" table,
- its **row** in `docs/knowledge/codemap.md` and its
  `docs/knowledge/skills/<name>-index.md`,
- its **dependency claims** in the README and the skill's own `README.md`
  versus the actual `scripts/requirements.txt` (or "no dependencies" claims
  versus whether a `requirements.txt` exists),
- the **slash-command** description in `commands/<slug>.md` versus what the
  skill now does.

Also sanity-check the cross-cutting docs against reality:

- `README.md` "Repository layout" tree — does it still match the real tree
  (new top-level dirs/files, renamed ones)?
- `docs/knowledge/architecture.md` — does the "LLM understands / script
  transforms" description still hold for every skill, including any new one?
- `docs/knowledge/codemap.md` "Dev tooling" table — are all hooks/scripts
  listed?

Flag a semantic drift only when the prose genuinely no longer fits the code —
not for harmless wording differences.

### Step 3 — Propose fixes

Present, in chat:

1. **Mechanical findings** — the script's errors and warnings, each with the
   exact file + the one-line fix.
2. **Semantic findings** — the description/code mismatches you found, quoting
   the stale sentence and the corrected wording.
3. **Where each fix goes** — exact file and table/section.

Then ask the user to approve. They may take a subset, edit wording, or
decline.

### Step 4 — Apply approved fixes

Only after approval:

- Edit only the docs. Do not change skill behaviour or scripts to make a doc
  true — fix the doc to match the code (unless the user says the code is what
  drifted, in which case confirm before touching code).
- Match each file's existing table shape, heading style, and tone.
- If a version bump is warranted (per the user's global rules, adding or
  changing a feature is a minor bump), update `.claude-plugin/plugin.json`.

### Step 5 — Re-run and report

Re-run the checker to confirm it now exits clean, then tell the user what was
changed and in which files so they can review the diff.

## Notes

- The script is the single source of truth for mechanical checks — the Stop
  hook (`.claude/hooks/check-docs-drift.sh`) runs the same script after any
  turn that touches catalog files, so mechanical drift is caught even when
  this skill is not explicitly invoked. This skill adds the semantic pass and
  the guided fix-up.
- The script is a plain CLI: `--json` for machine output, `--strict` to treat
  warnings as errors (handy in CI), `--root DIR` to point at another checkout.
- Read-first, write-on-approval: the analysis stays in chat; only approved
  edits are persisted.
- This skill lives in `.claude/skills/` (project-level), not `skills/` — it is
  repo-internal dev tooling and is not exported to users who install the
  plugin.
