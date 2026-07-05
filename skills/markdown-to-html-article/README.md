# markdown-to-html-article

Turn long AI-generated markdown into a single self-contained HTML article optimized for human reading — a magazine-style long read with a hero image, an article lede, deliberate typography, pull quotes, quiet marginal asides, syntax-highlighted code, inline concept tooltips, and dark mode.

Designed to be triggered automatically when Claude is about to dump a long markdown artifact (code review, implementation plan, spec, research report) on the user, or invoked manually with a markdown source.

## Output

A single `.html` file written to `./claude-articles/<timestamp>-<slug>.html` in the user's current working directory. The file is fully self-contained: all CSS / JS / hero SVG is inlined, so you can move it, archive it, or attach it to a ticket without breaking it. Image URLs (`http(s)://`) remain as links and need network to display; local image paths are inlined as base64.

## Dependencies — none

The renderer is **standard-library Python** (3.10+); there is nothing to install. The only bundled asset is [highlight.js](https://highlightjs.org/), inlined into the output automatically when the article contains code. The `bleach` / `markdown` / `pygments` / `jinja2` stack the old report renderer needed is gone: the body is converted by a small escape-first markdown-subset converter (`md_subset.py`) whose only output markup is what it emits itself, so no HTML sanitizer is required for the body; the hero SVG passes through a stdlib whitelist sanitizer (`svg_sanitizer.py`).

## How Claude uses it

1. The skill dispatches the bundled **`markdown-article-analyst` sub-agent**, which reads the source markdown and produces a `metadata.json`. Crucially, this includes a **rewritten prose `body_markdown` for each section** — the source is distilled and re-authored into flowing article prose, not copy-pasted. The metadata also carries the lede, per-section deks, sparing verbatim pull quotes, quiet callouts, and concept explanations. The agent and the metadata schema are documented in [`agents/markdown-article-analyst.md`](../../agents/markdown-article-analyst.md).
2. A deterministic verifier (`scripts/verify_fidelity.py`, stdlib-only) checks the metadata against the source — section coverage, verbatim code blocks, pull quotes, fact-token retention, and likely raw HTML in a body. On errors the analyst is asked to repair its metadata (at most two rounds) before anything is rendered.
3. The renderer script reads the source plus `metadata.json` and emits a self-contained HTML article, converting each section's `body_markdown` with the escape-first subset converter. Code blocks are always reproduced verbatim.
4. The main agent runs the renderer and relays the `file://` path back to the user.

The split is deliberate and three-way: the **analyst sub-agent** does the *understanding and editing* (it rewrites the prose), the **scripts** do the deterministic *transformation* (markdown subset → styled HTML), and the **skill** orchestrates the two. The `metadata.json` is the clean contract between them, which keeps the scripts self-testable and the comprehension work isolated in its own agent context.

## File layout

```
markdown-to-html-article/
├── SKILL.md                  # Skill description + workflow
├── README.md                 # this file
├── scripts/
│   ├── render_article.py     # renderer; CLI: <md> <metadata.json> <out.html> [--image-base DIR]
│   ├── md_subset.py          # escape-first markdown-subset → HTML converter (--selftest)
│   ├── svg_sanitizer.py      # stdlib whitelist sanitizer for the hero SVG (--selftest)
│   └── verify_fidelity.py    # fidelity checker; CLI: <md> <metadata.json> [--json]
├── templates/
│   └── article.html          # string.Template page shell (@@ delimiter) + interactivity JS
├── styles/
│   └── article.css           # magazine article layout, dark mode
└── vendor/                   # inlined into the HTML at render time, only when code is present
    ├── highlight.min.js
    ├── highlight-github.min.css
    └── highlight-github-dark.min.css
```

## Standalone CLI usage

All four scripts are plain stdlib CLIs — no install, useful for testing changes without Claude.

Renderer (prints the absolute output path on stdout):

```bash
python scripts/render_article.py <markdown_path> <metadata.json> <output.html> [--image-base DIR]
```

Fidelity verifier (exit 0 = clean or warnings only, 1 = fidelity errors, 2 = usage/IO error):

```bash
python scripts/verify_fidelity.py <markdown_path> <metadata.json> [--json]
```

The two conversion helpers each carry a self-test that doubles as their spec:

```bash
python scripts/md_subset.py --selftest
python scripts/svg_sanitizer.py --selftest
```

## Customizing

- **Visual tweaks** — edit `styles/article.css`. CSS variables at the top control colors, fonts, and spacing (light + dark).
- **Page structure** — edit `templates/article.html`. Inline JS at the bottom handles the theme toggle, code copy, scroll progress, and active-section tracking. The template uses `string.Template` with an `@@` delimiter; the placeholder set is fixed by `render_article.py`.
- **Body grammar** — the accepted `body_markdown` subset lives in `scripts/md_subset.py` (and its self-test). Anything outside the subset, including raw HTML, renders as escaped literal text.
- **Trigger sensitivity** — edit the `description` field in [`SKILL.md`](./SKILL.md) frontmatter.

## Limits

- The verifier and renderer key off *exact heading text match*. If two H2s share the same heading, append a discriminator (e.g., `... (cont.)`) to disambiguate.
- The body subset is deliberately small (see `md_subset.py`). Underscore emphasis, nested emphasis inside link labels, and list nesting deeper than one level are out of scope by design; raw HTML is always escaped.
