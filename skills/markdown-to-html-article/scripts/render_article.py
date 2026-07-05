#!/usr/bin/env python3
"""Render markdown + analyst metadata.json into a self-contained HTML article.

Stdlib only — no pip installs. The analyst's body_markdown is converted by
the escape-first md_subset converter, so no HTML sanitizer is needed for the
body; the hero SVG goes through svg_sanitizer's whitelist.

Usage:
    python render_article.py <markdown_path> <metadata_json_path> <output_html_path> [--image-base DIR]
"""
from __future__ import annotations

import argparse
import base64
import html as html_lib
import json
import mimetypes
import re
import sys
from pathlib import Path
from string import Template
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import md_subset  # noqa: E402
import svg_sanitizer  # noqa: E402

SKILL_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = SKILL_ROOT / "templates"
STYLES_DIR = SKILL_ROOT / "styles"
VENDOR_DIR = SKILL_ROOT / "vendor"

CALLOUT_LEVELS = ("key", "warning", "note")


class _Tpl(Template):
    delimiter = "@@"


def esc(value) -> str:
    return html_lib.escape(str(value), quote=True)


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def read_metadata(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        die(f"cannot read metadata JSON: {exc}")
    if not isinstance(data, dict):
        die("metadata JSON must be a single object")
    data.setdefault("title", "Untitled")
    data.setdefault("slug", "article")
    data.setdefault("lang", "en")
    data.setdefault("lede", "")
    data.setdefault("estimated_read_minutes", 0)
    data.setdefault("sections", [])
    data.setdefault("callouts", [])
    data.setdefault("concepts", [])
    data.setdefault("hero_image_svg", "")
    data.setdefault("hero_image_path", "")
    for idx, s in enumerate(data["sections"]):
        s.setdefault("level", 2)
        s.setdefault("summary", "")
        s.setdefault("pull_quotes", [])
        if not (s.get("body_markdown") or "").strip():
            die(
                f"section {s.get('id', idx)!r} has empty body_markdown — "
                "the analyst must supply rewritten prose for every section"
            )
    for c in data["callouts"]:
        if c.get("level") not in CALLOUT_LEVELS:
            c["level"] = "note"
    return data


def inline_local_images(html: str, md_dir: Path) -> str:
    """Inline non-URL <img src> targets as base64 data URIs (ported behavior)."""

    def repl(match: re.Match) -> str:
        src = match.group(1)
        parsed = urlparse(src)
        if parsed.scheme in ("http", "https", "data"):
            return match.group(0)
        src_fs = html_lib.unescape(src)
        candidate = (md_dir / src_fs).resolve() if not Path(src_fs).is_absolute() else Path(src_fs)
        if not candidate.exists() or not candidate.is_file():
            return f'<span class="img-missing">[image not found: {esc(src_fs)}]</span>'
        mime = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        encoded = base64.b64encode(candidate.read_bytes()).decode("ascii")
        return match.group(0).replace(f'src="{src}"', f'src="data:{mime};base64,{encoded}"')

    return re.sub(r'<img[^>]*\ssrc="([^"]+)"[^>]*>', repl, html)


def wrap_code_blocks(html: str) -> str:
    """Wrap converter-emitted <pre> blocks with a header + copy button."""

    def repl(match: re.Match) -> str:
        block = match.group(0)
        lang_match = re.search(r'class="language-([a-zA-Z0-9_+\-]+)"', block)
        lang = lang_match.group(1) if lang_match else "code"
        return (
            '<div class="code-block">'
            '<div class="code-block__header">'
            f'<span class="code-block__lang">{esc(lang)}</span>'
            '<button type="button" class="code-block__copy">Copy</button>'
            "</div>"
            f"{block}"
            "</div>"
        )

    return re.sub(r"<pre>.*?</pre>", repl, html, flags=re.DOTALL)


SKIP_PROTECT_PATTERNS = [
    re.compile(r"<pre[\s\S]*?</pre>", re.IGNORECASE),
    re.compile(r"<code[\s\S]*?</code>", re.IGNORECASE),
    re.compile(r"<h[1-6][\s\S]*?</h[1-6]>", re.IGNORECASE),
    re.compile(r"<a\b[\s\S]*?</a>", re.IGNORECASE),
    re.compile(r'<span class="gloss"[\s\S]*?</span></span>'),
]
TAG_SPLIT_RE = re.compile(r"(<[^>]+>)")
PLACEHOLDER_RE = re.compile(r"@@GLOSS_SKIP_(\d+)@@")


def _build_tooltip_html(plain: str, analogy: str) -> str:
    parts = [
        '<span class="gloss__tip" role="tooltip">',
        '<span class="gloss__tip-label">Plain</span>',
        esc(plain or ""),
    ]
    if analogy:
        parts.append('<span class="gloss__tip-label gloss__tip-label--alt">Analogy</span>')
        parts.append(esc(analogy))
    parts.append("</span>")
    return "".join(parts)


def insert_glossary_terms(html: str, concepts: list[dict]) -> str:
    """Wrap plain-text occurrences of glossary terms with hover tooltips.

    Ported unchanged from the old renderer: skips <pre>, <code>, headings,
    <a>, and existing .gloss wrappers; longest terms first; word-boundary
    guards that also work for non-ASCII terms.
    """
    if not concepts:
        return html

    sorted_concepts = sorted(
        (c for c in concepts if c.get("term", "").strip()),
        key=lambda c: len(c["term"]),
        reverse=True,
    )
    for c in sorted_concepts:
        term = c["term"].strip()
        tip_html = _build_tooltip_html(c.get("plain_explanation", ""), c.get("analogy", ""))
        stash: list[str] = []

        def stash_sub(m: re.Match) -> str:
            stash.append(m.group(0))
            return f"@@GLOSS_SKIP_{len(stash) - 1}@@"

        protected = html
        for pat in SKIP_PROTECT_PATTERNS:
            protected = pat.sub(stash_sub, protected)

        first, last = term[0], term[-1]
        left_guard = r"(?<!\w)" if first.isalnum() or first == "_" else ""
        right_guard = r"(?!\w)" if last.isalnum() or last == "_" else ""
        term_re = re.compile(left_guard + re.escape(term) + right_guard)

        def wrap(m: re.Match) -> str:
            return (
                f'<span class="gloss" tabindex="0" role="button" '
                f'aria-label="glossary: {esc(term)}">'
                f"{m.group(0)}{tip_html}</span>"
            )

        parts = TAG_SPLIT_RE.split(protected)
        for i in range(0, len(parts), 2):
            if parts[i]:
                parts[i] = term_re.sub(wrap, parts[i])
        protected = "".join(parts)
        html = PLACEHOLDER_RE.sub(lambda m: stash[int(m.group(1))], protected)
    return html


def build_hero_image_html(meta: dict, md_dir: Path) -> str:
    svg = (meta.get("hero_image_svg") or "").strip()
    path_str = (meta.get("hero_image_path") or "").strip()
    if path_str:
        p = Path(path_str)
        if not p.is_absolute():
            p = (md_dir / path_str).resolve()
        if p.exists() and p.is_file():
            mime = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
            if mime == "image/svg+xml":
                try:
                    return svg_sanitizer.sanitize_svg(p.read_text(encoding="utf-8"))
                except OSError:
                    pass
            data = base64.b64encode(p.read_bytes()).decode("ascii")
            return f'<img src="data:{mime};base64,{data}" alt="{esc(meta.get("title", ""))}">'
    if svg:
        return svg_sanitizer.sanitize_svg(svg)
    return ""


def build_sections_html(meta: dict, img_base: Path) -> str:
    callouts_by_section: dict[str, list[dict]] = {}
    for c in meta["callouts"]:
        callouts_by_section.setdefault(c.get("section_id", ""), []).append(c)

    blocks: list[str] = []
    for s in meta["sections"]:
        level = min(max(int(s.get("level", 2)), 2), 4)
        parts = [f'<article class="section" id="{esc(s["id"])}">']
        parts.append(f'<h{level} class="section__heading">{esc(s["heading"])}</h{level}>')
        if s.get("summary"):
            parts.append(f'<p class="section__dek">{esc(s["summary"])}</p>')
        for c in callouts_by_section.get(s["id"], []):
            parts.append(
                f'<aside class="aside aside--{c["level"]}">'
                f'<span class="aside__label">{c["level"]}</span>'
                f"{esc(c.get('text', ''))}</aside>"
            )
        for q in s.get("pull_quotes", [])[:1]:
            parts.append(f'<blockquote class="pullquote">{esc(q)}</blockquote>')
        body = md_subset.convert(s["body_markdown"])
        body = inline_local_images(body, img_base)
        body = wrap_code_blocks(body)
        body = insert_glossary_terms(body, meta["concepts"])
        parts.append(f'<div class="section__body prose">{body}</div>')
        parts.append("</article>")
        blocks.append("\n".join(parts))
    return "\n\n".join(blocks)


def build_toc_html(meta: dict) -> str:
    items = [
        f'<li class="toc__item" data-section-id="{esc(s["id"])}">'
        f'<a class="toc__link" href="#{esc(s["id"])}">{esc(s["heading"])}</a></li>'
        for s in meta["sections"]
    ]
    return "\n".join(items)


def build_glossary_html(meta: dict) -> str:
    if not meta["concepts"]:
        return ""
    parts = ['<section class="glossary"><h2 class="glossary__title">Glossary</h2><dl>']
    for c in meta["concepts"]:
        parts.append(f"<dt>{esc(c.get('term', ''))}</dt>")
        dd = esc(c.get("plain_explanation", ""))
        if c.get("analogy"):
            dd += f'<br><em class="glossary__analogy">Analogy: {esc(c["analogy"])}</em>'
        parts.append(f"<dd>{dd}</dd>")
    parts.append("</dl></section>")
    return "".join(parts)


def build(markdown_path: Path, metadata_path: Path, output_path: Path,
          image_base_dir: Path | None = None) -> Path:
    meta = read_metadata(metadata_path)
    img_base = image_base_dir or markdown_path.parent

    sections_html = build_sections_html(meta, img_base)
    has_code = "<pre>" in sections_html

    hl_js = ""
    if has_code:
        hl_path = VENDOR_DIR / "highlight.min.js"
        if hl_path.exists():
            hl_js = hl_path.read_text(encoding="utf-8")
        else:
            print("WARN: vendor/highlight.min.js missing — rendering without "
                  "syntax highlighting", file=sys.stderr)
    scripts_html = (
        f"<script>{hl_js}</script>\n<script>hljs.highlightAll();</script>" if hl_js else ""
    )

    meta_line_bits = []
    if meta["estimated_read_minutes"]:
        meta_line_bits.append(f'<span>{esc(meta["estimated_read_minutes"])} min read</span>')
    meta_line_bits.append(f'<span>{len(meta["sections"])} sections</span>')

    template = _Tpl((TEMPLATES_DIR / "article.html").read_text(encoding="utf-8"))
    html = template.safe_substitute(
        lang=esc(meta["lang"]),
        title=esc(meta["title"]),
        css=(STYLES_DIR / "article.css").read_text(encoding="utf-8"),
        hl_light=(VENDOR_DIR / "highlight-github.min.css").read_text(encoding="utf-8"),
        hl_dark=(VENDOR_DIR / "highlight-github-dark.min.css").read_text(encoding="utf-8"),
        hero_html=build_hero_image_html(meta, img_base),
        lede_html=esc(meta["lede"]),
        meta_line=" · ".join(meta_line_bits),
        toc_html=build_toc_html(meta),
        sections_html=sections_html,
        glossary_html=build_glossary_html(meta),
        scripts_html=scripts_html,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown", type=Path)
    parser.add_argument("metadata", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--image-base", type=Path, default=None,
        help="Base directory for resolving relative image paths. Defaults to "
             "the markdown file's folder; pass the ORIGINAL markdown_dir when "
             "the source is a temp file so relative images still resolve.",
    )
    args = parser.parse_args()
    if not args.markdown.exists():
        die(f"markdown not found: {args.markdown}")
    if not args.metadata.exists():
        die(f"metadata not found: {args.metadata}")
    out = build(args.markdown, args.metadata, args.output, image_base_dir=args.image_base)
    print(str(out.resolve()))


if __name__ == "__main__":
    main()
