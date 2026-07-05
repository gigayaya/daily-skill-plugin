# markdown-to-html-article

Converts long markdown into a self-contained magazine-style HTML article (hero, lede, pull quotes, syntax highlighting, dark mode). Stdlib-only scripts; the only bundled assets are highlight.js and its two themes.

| Path | What it is | When to read |
|---|---|---|
| `skills/markdown-to-html-article/SKILL.md` | Frontmatter + orchestration workflow: resolve source → dispatch analyst → verify → render → report | Adjusting trigger conditions or the orchestration flow |
| `agents/markdown-article-analyst.md` | Sub-agent that owns Step 2: reads/understands/rewrites the article and writes `metadata.json` (carries the metadata schema, body-rewriting rules, body subset, SVG rules, language handling) | Changing how the article is understood or rewritten — rewrite intensity, metadata spec, SVG/glossary rules |
| `skills/markdown-to-html-article/README.md` | User-facing docs, standalone CLI usage, zero-dependency note | Changing user-visible behaviour or CLI usage |
| `commands/html-article.md` | Slash command `/html-article` that invokes this skill | Renaming the command, editing its `description` / `argument-hint` / invocation prompt |
| `skills/markdown-to-html-article/scripts/render_article.py` | Main renderer: reads markdown + metadata.json, emits self-contained HTML (escape-first body conversion, glossary tooltips, SVG hero) | Changing transformation logic, fixing script bugs |
| `skills/markdown-to-html-article/scripts/md_subset.py` | Escape-first markdown-subset → HTML converter; every source run is HTML-escaped before any tag is emitted (`--selftest`) | Changing the accepted `body_markdown` grammar |
| `skills/markdown-to-html-article/scripts/svg_sanitizer.py` | Stdlib whitelist sanitizer for the analyst-authored hero SVG (`--selftest`) | Changing which SVG tags/attributes are allowed |
| `skills/markdown-to-html-article/scripts/verify_fidelity.py` | Deterministic fidelity checker: compares metadata.json against the source (section coverage, verbatim code blocks, pull quotes, fact tokens, raw-html warning) before rendering | Changing what counts as a fidelity error/warning |
| `skills/markdown-to-html-article/templates/article.html` | `string.Template` page shell (`@@` delimiter) + interactivity JS | Changing overall article structure or the page shell |
| `skills/markdown-to-html-article/styles/article.css` | Core stylesheet: magazine layout, dark mode, serif/mono type system | Changing visual style or colour rules |
| `skills/markdown-to-html-article/vendor/highlight.min.js` | highlight.js library (inlined only when code blocks present) | Upgrading the syntax-highlight library |
| `skills/markdown-to-html-article/vendor/highlight-github.min.css` | Light-mode code highlight theme | Swapping the light-mode theme or upgrading |
| `skills/markdown-to-html-article/vendor/highlight-github-dark.min.css` | Dark-mode code highlight theme | Swapping the dark-mode theme or upgrading |
