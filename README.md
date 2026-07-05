# gigachang-skills

A personal collection of [Claude Code](https://docs.claude.com/en/docs/claude-code/overview) skills for daily workflows. Each skill is a small, focused capability that Claude can invoke automatically (via skill description matching) or that you can trigger manually.

## Skills in this plugin

Each skill auto-triggers when its `description` matches what you're asking for, or you can run the matching slash command (see [Slash commands](#slash-commands) below).

| Skill | What it does |
|---|---|
| [markdown-to-html-article](./skills/markdown-to-html-article/) | Converts long AI-generated markdown (code reviews, plans, specs) into a single self-contained HTML article — hero image, article lede, magazine typography, pull quotes, syntax highlighting, dark mode. Zero Python dependencies |
| [session-reflection](./skills/session-reflection/) | Reflects on the current session — finds where Claude's output was rejected or corrected, distills the root causes, and proposes project rules (into `CLAUDE.md` or your existing rule system) so the same mistake doesn't recur. No dependencies |
| [ab-review](./skills/ab-review/) | Two-sided "AB" code review — dispatches a Pro reviewer (arguing the change is mergeable) and a Con reviewer (arguing it is not) in parallel, each citing concrete evidence from the diff, then verifies every cited snippet against the repo before the main agent judges. Manual-trigger, no dependencies |
| [scope-research](./skills/scope-research/) | Surveys the codebase against a proposed requirement and reports the concrete facts a reader needs to assess scope themselves — affected files, callers, prior similar changes, current test state, conventions in use, with honest per-touchpoint LOC ranges. States facts only, never issues t-shirt sizes or risk ratings. Manual-trigger, no dependencies |

---

## Installation

### 1. Install the plugin in Claude Code

This plugin is published as its own single-plugin marketplace at [`gigayaya/gigachang-skills`](https://github.com/gigayaya/gigachang-skills). Install in two steps inside any Claude Code session:

```text
/plugin marketplace add gigayaya/gigachang-skills
/plugin install gigachang-skills@gigachang-skills
```

(Yes, the name is repeated — `<plugin-name>@<marketplace-name>`, both happen to be `gigachang-skills`.)

After install, `${CLAUDE_PLUGIN_ROOT}` resolves to the cached plugin directory. Every skill in this repo uses that variable so paths stay portable.

#### Updating

```text
/plugin marketplace update gigachang-skills
/plugin update gigachang-skills@gigachang-skills
```

You can also enable auto-update under `/plugin` → **Marketplaces**.

### 2. Per-skill dependencies

No skill in this plugin needs third-party libraries — they run on standard-library Python or pure LLM + built-in tools, so there is nothing to install beyond the plugin itself.

#### markdown-to-html-article — no dependencies

The renderer is standard-library Python; nothing to install. Bundled highlight.js is inlined automatically when the article contains code.

---

## Slash commands

Every skill has a matching slash command so you can invoke it explicitly instead of relying on auto-trigger:

| Command | Skill | Use it for |
|---|---|---|
| `/html-article [path]` | `markdown-to-html-article` | Convert a markdown file (or the latest long markdown in chat) into an HTML article |
| `/reflect [focus]` | `session-reflection` | Reflect on this session and propose project rules |
| `/ab-review [scope]` | `ab-review` | Run a two-sided adversarial review of your code changes |
| `/scope-research [requirement]` | `scope-research` | Survey the codebase against a requirement and report touchpoints + facts |

Each command accepts an optional argument (described in the command's `argument-hint`); leave it blank to use context already in the conversation.

---

## Verifying the install

Open a Claude Code session and ask:

> List the skills you have available.

All four skills (`markdown-to-html-article`, `session-reflection`, `ab-review`, `scope-research`) should appear in the list. To smoke-test `markdown-to-html-article` end-to-end, ask Claude to:

> Convert this README into an HTML article.

You should see Claude invoke the skill, run the renderer, and hand you back a `file://` link to a `.html` file in `./claude-articles/`.

---

## Repository layout

```
gigachang-skills/
├── .claude-plugin/
│   ├── plugin.json                # plugin manifest (name, version, author, ...)
│   └── marketplace.json           # single-plugin marketplace entry (for /plugin install)
├── agents/                        # plugin-bundled sub-agent definitions (auto-discovered)
│   ├── ab-review-pro.md
│   ├── ab-review-con.md
│   ├── markdown-article-analyst.md
│   └── scope-research-surveyor.md
├── commands/                      # slash-command definitions (auto-discovered)
│   ├── ab-review.md
│   ├── html-article.md
│   ├── reflect.md
│   └── scope-research.md
├── skills/
│   └── <skill-name>/
│       ├── SKILL.md               # frontmatter (name + description) + workflow
│       ├── README.md              # human-facing docs + standalone CLI usage
│       └── ...                    # scripts, templates, assets per skill
├── .claude/                       # repo-private dev tooling (NOT exported with the plugin)
│   ├── settings.json              # Stop-hook wiring for this repo
│   ├── hooks/                     # check-skill-completion.sh, check-docs-drift.sh
│   ├── commands/                  # /docs-drift (project-level command)
│   └── skills/
│       └── docs-drift/            # docs-drift skill (project-level, loads only in this repo)
├── CLAUDE.md                      # project rules read by Claude Code each session
├── LICENSE
└── README.md                      # this file
```

Add a new skill by creating `skills/<your-skill>/SKILL.md` with a `name` and `description` in YAML frontmatter — Claude Code auto-discovers it on next session start. Same for sub-agents in `agents/` and slash commands in `commands/`.

---

## License

MIT — see [LICENSE](./LICENSE).
