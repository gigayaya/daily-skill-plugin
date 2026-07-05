# scope-research

A codebase **scope-research** skill. Given a proposed requirement, Claude
surveys the current codebase and returns a structured report of the concrete
facts a reader needs to assess scope themselves: which files/areas the change
would touch, an honest **LOC range** per touchpoint (and their additive sum
at the top of the report), and what is true about each touchpoint right now
(callers, prior similar changes, current test state, conventions in use,
data/interface contracts).

The skill deliberately **does not issue a verdict** — no t-shirt size, no
time estimate, no risk rating, and no single LOC number. A scope conclusion
expressed as a single label hides the reasoning behind it; naming the facts
and giving honest per-touchpoint ranges gives the reader something they can
actually weigh.

Triggered manually when you ask Claude to research the scope of a
requirement, or via `/scope-research`. It never auto-runs.

## How Claude uses it

1. **Anchors the requirement** — reads the inline description, file path, or
   pasted spec the user provided. If the requirement is too vague to
   research, Claude asks clarifying questions before going to the codebase.
2. **Detects project code-navigation conventions** — checks the project's
   rule files (`CLAUDE.md`, `AGENTS.md`, `.cursor/rules/`, README, …) for
   any prescribed code-search system (e.g. a Serena-style MCP server, a
   custom indexer, a documented architecture map). If one is prescribed,
   Claude uses it instead of the generic Read/Grep/Glob path.
3. **Initial scan** — main agent locates likely-affected areas directly.
4. **Targeted exploration** — for broader scope, dispatches
   `scope-research-surveyor` agents in parallel (typically 1–3, as many
   as the requirement honestly warrants — no hard cap), each with a
   distinct search focus (callers, prior similar changes, test state,
   conventions).
   The surveyor is a bundled plugin agent defined in
   `agents/scope-research-surveyor.md`; it carries its own stance, tool
   boundaries, no-fabrication rule, and required output format (per-fact
   `Change size` LOC ranges and a `Coverage` paragraph).
5. **Resolves uncertainty** — anything still unclear that would change the
   report gets surfaced as a clarifying question to the user. Claude keeps
   asking until there are no remaining material questions.
6. **Writes the report** — restates the requirement, lists affected areas /
   files with role notes and per-touchpoint LOC ranges, sums the ranges
   into an `Estimated total change` line at the top, and states relevant
   facts neutrally. If the report is long, Claude suggests running
   `/html-article` on it.

Like `ab-review`, this is **pure orchestration** — no transformation script.

## Required dependencies

**None.** The skill uses Read/Grep/Glob, `git`, and the `Agent` tool only —
no `pip install` step and no runtime script.

## File layout

```
scope-research/
├── SKILL.md     # skill description + workflow
└── README.md    # this file
```

## Notes

- Manual-trigger only — Claude never auto-invokes it.
- The skill never issues a verdict; it surfaces facts and leaves the
  conclusion to the reader.
- It is read-only — it never writes code, never edits files outside the
  report it returns in chat, never commits.
- The report stays in the conversation; pair with `/html-article` for a
  saved, readable artifact if you want one.
