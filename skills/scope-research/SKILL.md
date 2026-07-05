---
name: scope-research
description: Use when the user explicitly asks to research the scope of a requirement or proposed change against the current codebase — e.g. "research the scope of this requirement", "what would adding X touch in this codebase", "do scope research on this spec", "/scope-research". Surveys the codebase to surface concrete facts about which files/areas a change would touch and the relevant facts about each touchpoint (callers, prior similar changes, current test state, conventions in use, data/interface contracts), with an honest LOC range per touchpoint. Presents facts neutrally — does not assign t-shirt sizes, time estimates, or risk ratings. When unsure about something material, asks the user clarifying questions before writing the report. Manual-trigger only — never auto-invoke. Skip for trivial single-file or one-line changes where research adds no value.
---

# Scope Research

Survey the codebase against a proposed requirement and report the concrete
facts a reader would need to assess scope themselves — which areas would be
touched, and what is true about each of those touchpoints right now. The
skill states facts; the reader draws the conclusions.

A scope assessment expressed as a t-shirt size or a single LOC number hides
the reasoning that produced it. Naming the touchpoints — each with an honest
LOC range and the facts around it (callers, prior changes, test state,
conventions) — gives the reader something they can actually weigh, and
surfaces the questions worth asking before the work begins.

## When to invoke

- **Manual only.** The user explicitly asks to research the scope of a
  requirement, or runs `/scope-research`.
- **Never auto-invoke.**
- **Skip** trivial single-file or one-line changes where research adds
  nothing.
- The skill **never issues a verdict** — no t-shirt size, no time estimate,
  no risk rating. LOC change appears as honest ranges per touchpoint (e.g.
  `~5–20 lines`), never as a single number or bucket label. It surfaces
  facts only.

## Workflow

### Step 1 — Anchor the requirement

The requirement can arrive as:

- an **inline description** in the chat,
- a **local file path** the user gave (e.g. `specs/new-feature.md`) — read it
  directly,
- a **pasted ticket body / spec** in the chat.

Read what the user provided. If the requirement is too vague to research
(e.g. "make the app faster"), ask clarifying questions with
`AskUserQuestion` **before** going to the codebase. Do not guess at intent.

### Step 2 — Detect project code-navigation conventions

Before exploring, check the project's rule files for any prescribed
code-search system — an MCP server (e.g. Serena, a code-index server), a
custom indexer, a documented architecture map, or any other navigation
convention. Look in this order:

1. `CLAUDE.md` (repo root, then `.claude/CLAUDE.md`)
2. `AGENTS.md`
3. `.cursor/rules/` or `.cursorrules`
4. `.github/copilot-instructions.md`
5. `README.md` / `CONTRIBUTING.md` — sections on code navigation

If the project prescribes a tool, **use it** instead of (or in addition to)
the generic Read/Grep/Glob path. If nothing is prescribed, fall back to the
generic tools.

### Step 3 — Initial scan

The main agent does a first pass to locate likely-affected areas: grep for
the key nouns/verbs from the requirement, read the top hits, and form a
rough picture of where the change would land.

### Step 4 — Targeted exploration

If the scope is broader than one area, dispatch **`scope-research-surveyor`
agents in parallel** (single message, multiple `Agent` tool calls) —
typically 1–3, but as many as the requirement honestly warrants. Each
surveyor gets a distinct, specific search focus — examples:

- "Callers of `<symbol>` and the call sites' surrounding context."
- "Prior similar changes in git history (`git log -S`, `git log --grep`)."
- "Current test state for module `<X>` — which test files cover it, what
  they assert, what they do not."
- "Conventions currently used in `<area>` for `<concern>`."

Two principles govern how many to dispatch — there is no hard cap:

1. **Each focus must be load-bearing.** A focus that could merge into
   another without losing clarity should merge — don't open a surveyor for
   it. A surveyor is one full inference run plus a report you have to
   read; it has to earn that cost.
2. **You will have to integrate every report.** More surveyors = harder
   synthesis. If you find yourself wanting more than ~4–5 surveyors,
   consider whether the requirement should be researched in stages
   instead of one wide fan-out.

Pass each surveyor: the requirement (as currently understood), its specific
focus, the repository path, and any context already gathered. The
surveyor's contract — stance, tool boundaries, no-fabrication rule, the
required `Focus` / `Facts` / `Coverage` output format, and the per-fact
`Change size` LOC-range field — is defined in
`agents/scope-research-surveyor.md`. Do not re-specify any of that in the
dispatch call.

For tightly scoped requirements, skip this step entirely — the main
agent's direct exploration is enough.

### Step 5 — Resolve uncertainty

If anything material to the report is still unclear after exploration, ask
the user with `AskUserQuestion`. Examples of material uncertainty:

- The requirement could be implemented in two genuinely different places and
  the choice would change the touchpoint list.
- A key behaviour the requirement implies is not specified (e.g. "rate
  limiting" — per user? per IP? per endpoint?).
- The codebase has two plausible interpretations of a term the requirement
  uses.

Keep asking until **no remaining material questions**. Uncertainty is not an
output category — it is resolved before the report exists.

### Step 6 — Write the report

Present the report in chat in this shape:

#### Requirement (one paragraph)

Restate what the skill understood the requirement to be, after any
clarifications. The user can correct here before reading further.

#### Estimated total change

A single line at the top of the report, after the requirement restatement:

> **Estimated total change: ~A–B lines**

`A` and `B` are the sums of the lower and upper bounds of the per-touchpoint
`Change size` ranges below. This is an additive sum of honest per-touchpoint
ranges, **not** a grand-judgment "size". If any touchpoint's Change size is
`n/a`, exclude it from the sum and say so on a follow-up line.

#### Affected areas / files

A list. Each entry:

- **`<path>`** — *modify* / *add* / *delete* — Change size: ~X–Y lines —
  one sentence on the role this file plays in the change.

Group by subsystem if helpful. Use `file:line` references where a specific
location matters. The `Change size` per touchpoint mirrors what the
surveyors reported in their `Facts` items — use their numbers, do not
re-estimate.

#### Relevant facts

For each touchpoint (or for the change overall), state neutral facts:

- callers / dependents of an affected symbol (`file:line` references)
- prior similar changes in git history (commit hashes + one-line summaries)
- current test coverage state for the affected area
- existing conventions / patterns the change would intersect with
- data-shape, migration, or interface-contract facts

Facts are stated, not labelled as "risks" and not weighted. **Do not write
"this is risky because…" or "low risk".** Write the fact; the reader
decides.

#### End — cross-skill hint

If the report is long (≥150 lines, ≥5 H2/H3 sections, or simply a lot to
scan), suggest the user run `/html-article` on it. Otherwise skip the hint.

## Notes

- No script — pure LLM + Read/Grep/Glob + `Agent`. Same shape as `ab-review`.
- The skill is read-only: it never writes code, never edits files outside of
  the report it returns in chat, never commits.
- The report stays in the conversation. If the user wants a saved artifact,
  they can run `/html-article` on the report after the fact.
- No verdicts: no t-shirt size, no time estimate, no risk rating. LOC
  change appears only as honest per-touchpoint ranges (and their additive
  sum at the top of the report) — never as a single number or bucket. If
  the user asks for a t-shirt size or a single LOC number, restate this
  constraint and offer to surface more facts instead.
