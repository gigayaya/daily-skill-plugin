---
description: Check whether this plugin's docs have drifted from its code, and propose fixes
argument-hint: "[optional path to a checkout, defaults to this repo]"
---

Invoke the `docs-drift` skill: run the mechanical checker
(`.claude/skills/docs-drift/scripts/check_docs_drift.py`), then do the semantic pass —
compare each doc's description against what the code actually does — and report
both mechanical and semantic drift.

Target (optional checkout path): $ARGUMENTS

Do not edit any docs without explicit user approval.
