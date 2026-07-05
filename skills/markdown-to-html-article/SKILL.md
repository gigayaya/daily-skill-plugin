---
name: markdown-to-html-article
description: Use when about to present long or complex AI-generated markdown to the user — typically >150 lines, >5 H2 sections, or content like code reviews, implementation plans, specs, research reports. Also use when the user explicitly asks to convert a markdown source into a readable HTML article. Produces a single self-contained HTML article (hero image, article lede, magazine typography, pull quotes, quiet asides, syntax-highlighted code, inline concept tooltips, dark mode) saved to ./claude-articles/. Zero install — the renderer is stdlib-only Python. Skip for short, simple, or plain-text content where the conversion cost outweighs the reader's time savings.
---

# Markdown to HTML Article

Turn long AI-generated markdown into a human-friendly self-contained HTML article — a magazine-style long read with a hero image, an article lede, pull quotes, quiet marginal asides, and inline concept explanations.

**This skill rewrites, it does not photocopy.** The source markdown is raw material, not the final body. Each section is re-authored into flowing prose that reads like a well-edited tech article — not a bullet dump. The work splits in three: the `markdown-article-analyst` sub-agent does the *understanding and editing* (it reads the source and produces the rewritten `metadata.json`), the renderer does the deterministic HTML *transformation*, and this skill *orchestrates* the two. Copy-pasting the source verbatim into the article is the single most common failure mode and is explicitly wrong.

## When to invoke

**Auto-trigger heuristic** (use judgment, not strict thresholds):
- Output is ≥150 lines OR has ≥5 H2/H3 sections
- Content type is: code review, implementation plan, design spec, research report, audit, or similar long-form analysis
- The reader (user) clearly benefits from a top-to-bottom long read

**Manual trigger:** user explicitly asks ("convert this to an HTML article", "make a readable version", or hands you a markdown file/string).

**Skip when:**
- Content is short (<~80 lines)
- Content is conversational, a single answer, or plain-text-suitable
- User is mid-flow and doesn't want a side artifact

## Workflow

### Step 1 — Resolve the markdown source

The source can be:
- **A file path** the user provided → read it directly
- **A pasted markdown string** → write to `./claude-articles/.tmp-input.md`
- **Markdown you just produced** in this conversation → write to `./claude-articles/.tmp-input.md`

Note the `markdown_dir` (parent of the markdown file) — it's used to resolve relative image paths.

### Step 2 — Dispatch the analyst sub-agent (understand + rewrite + metadata)

The comprehension-heavy half — reading the source, understanding it, re-authoring each section into distilled prose, and producing `metadata.json` — is delegated to the bundled `markdown-article-analyst` sub-agent. You do **not** read and rewrite the article yourself.

In a single `Agent` call, dispatch `subagent_type: markdown-article-analyst` and pass it:

- the **markdown source path** from Step 1,
- the **`markdown_dir`** (parent of the source, for resolving relative image paths),
- the **metadata output path** it must write: `./claude-articles/.tmp-article.json`.

The agent already carries the full contract — the metadata schema, the body-rewriting rules, the body subset, the hero-SVG rules, the glossary rules, the same-language rule, and the no-fabrication rule — defined in `agents/markdown-article-analyst.md`. **Do not re-specify any of that here, and do not do the rewriting yourself.**

When it returns, it reports the metadata path it wrote, the `slug` it chose, the section count, estimated read minutes, the pull-quote count, and the language. Use the metadata path and slug in Steps 3–4, and the counts in your Step 5 message.

### Step 3 — Verify fidelity (mandatory)

The analyst is a rewriter, so its output must be checked, not trusted. Run
the verifier (standard-library Python, no install needed):

```bash
python ${CLAUDE_PLUGIN_ROOT}/skills/markdown-to-html-article/scripts/verify_fidelity.py \
  <markdown_path> ./claude-articles/.tmp-article.json --json
```

It compares the metadata against the source. **Errors** (exit 1): a source
H2/H3 section that no section covers, merges, or declares omitted; a
fabricated section heading; a source code block missing or altered in the
rewritten bodies; a `pull_quote` not verbatim in its section body.
**Warnings** (exit 0): declared omissions (with the analyst's reason), source
fact tokens (numbers, inline code, paths, URLs) missing from the rewritten
article, language drift, and `raw-html-in-body` — the analyst wrote a raw HTML
tag in a body. The renderer is escape-first, so any such tag renders as
literal text rather than markup; treat this as a warning the **main agent
judges** (real markup the author intended to render vs. a false positive like
prose containing `List<String>`).

Handle the result:

1. **No errors** → proceed to Step 4. Use judgment on warnings; mention
   notable ones (declared omissions, lost fact tokens, raw HTML in a body) in
   your Step 5 message.
2. **Errors** → send the full JSON failure summary back to the **same** analyst
   agent via `SendMessage`, asking it to repair the metadata file in place (its
   agent file defines the repair protocol). Re-run the verifier. At most
   **2** repair rounds.
3. **Still failing after 2 rounds** → show the user the unresolved errors and
   ask whether to render anyway (with the issues noted) or abort. Never
   silently render an article that failed verification.

### Step 4 — Run the renderer

The renderer is standard-library Python — nothing to install. Render, using
the metadata path the analyst wrote and the `<slug>` it returned:

```bash
python ${CLAUDE_PLUGIN_ROOT}/skills/markdown-to-html-article/scripts/render_article.py \
  <markdown_path> \
  ./claude-articles/.tmp-article.json \
  ./claude-articles/$(date +%Y%m%d-%H%M%S)-<slug>.html
```

**If the markdown source is a temp file** (a pasted string or markdown you
produced in chat, written to `./claude-articles/.tmp-input.md`), the source's
folder is no longer where its relative images live. Pass the original
`markdown_dir` from Step 1 so relative images still resolve:
```bash
  ... --image-base <markdown_dir>
```
When the source is a real file the user gave, omit the flag — it defaults to
the file's own folder.

The script prints the absolute output path on stdout. The metadata contract is unchanged — the renderer behaves identically whether the metadata was authored inline or by the sub-agent.

### Step 5 — Cleanup and report

- Delete the `.tmp-*.md` and `.tmp-*.json` files
- If `./claude-articles/` was just created, remind the user once: *"I created `./claude-articles/` for HTML articles — consider adding it to .gitignore."*
- Tell the user the article is ready and provide the `file://<absolute-path>` link they can cmd-click to open

Example final message:
> Article ready: `file:///Users/you/proj/claude-articles/20260705-143022-pr-review.html` (12 min read, 8 sections). Reads top-to-bottom like a magazine piece.

## Notes

- **The analyst sub-agent owns Step 2.** Reading, understanding, and rewriting the article — plus authoring `metadata.json` — all live in `agents/markdown-article-analyst.md`. This skill orchestrates (resolve source → dispatch agent → verify → render → report); it does not rewrite the article inline. If you need to change *how* the article is understood or rewritten (rewrite intensity, schema, subset, SVG/glossary rules), edit the agent file, not this one.
- **Zero dependencies.** The renderer is stdlib-only Python; there is no install step. The output is fully self-contained: opens offline, all CSS / JS / hero SVG inlined. Exception: image URLs (http/https) inside the markdown body remain as links and need network to display.
- **highlight.js is only inlined when there's at least one code block** — a pure-prose article carries no syntax-highlighting payload.
- **The body is escape-first.** `body_markdown` is converted by a small markdown-subset renderer that HTML-escapes every source run before emitting its own tags, so any raw HTML the analyst wrote (`<kbd>`, `<details>`, …) shows up as literal text — by design. The verifier warns on it in Step 3.
- **Hero SVG is sanitized** by a separate whitelist — `<script>`, event handlers, `style="…"` attrs, and unrecognized tags (plus any `href`/`src`) are stripped. Keep the SVG self-contained.
- **Glossary tooltips are pure CSS hover** (with keyboard focus support). They appear over body text; the bottom Glossary section is still rendered as a quick index.
