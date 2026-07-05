#!/usr/bin/env python3
"""md_subset.py — escape-first Markdown-subset to HTML converter.

Supports exactly the body_markdown subset of the markdown-to-html-article
skill: paragraphs, **bold**, *italic* (asterisk forms only), `inline code`,
[label](url) links, ![alt](src) images, ordered/unordered lists (one nesting
level), fenced code blocks with a language tag, blockquotes, pipe tables,
and --- horizontal rules. Anything else — including raw HTML — renders as
escaped literal text.

Escape-first: every piece of source text is HTML-escaped before any tag is
emitted, so the only markup in the output is what this module generates.
That property is what lets the renderer skip a sanitizer entirely.

Standard library only. Run `python md_subset.py --selftest` to check it.
"""
from __future__ import annotations

import html
import re
import sys

FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})\s*([^\s`]*)\s*$")
HR_RE = re.compile(r"^ {0,3}(-{3,}|\*{3,}|_{3,})\s*$")
QUOTE_RE = re.compile(r"^ {0,3}>\s?(.*)$")
LIST_ITEM_RE = re.compile(r"^(?P<indent>\s*)(?P<marker>[-*+]|\d{1,9}[.)])\s+(?P<text>.*)$")
TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")

CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
ITALIC_RE = re.compile(r"\*([^*\n]+)\*")
SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*):")
STASH_RE = re.compile("\x00(\\d+)\x00")


def _safe_href(url: str) -> bool:
    return bool(re.match(r"^(https?://|mailto:|#)", url, re.IGNORECASE))


def _safe_src(url: str) -> bool:
    m = SCHEME_RE.match(url)
    return m is None or m.group(1).lower() in ("http", "https", "data")


def _inline(raw: str) -> str:
    """Escape a text run, then apply inline markup on the escaped text."""
    text = html.escape(raw)
    stash: list[str] = []

    def keep(rendered: str) -> str:
        stash.append(rendered)
        return f"\x00{len(stash) - 1}\x00"

    # Code spans first — their content is protected from every later rule.
    text = CODE_SPAN_RE.sub(lambda m: keep(f"<code>{m.group(1)}</code>"), text)

    def img_sub(m: re.Match) -> str:
        alt, src = m.group(1), m.group(2)
        if not _safe_src(src):
            return m.group(0)
        return keep(f'<img src="{src}" alt="{alt}">')

    text = IMAGE_RE.sub(img_sub, text)

    def link_sub(m: re.Match) -> str:
        label, href = m.group(1), m.group(2)
        if not _safe_href(href):
            return m.group(0)
        return keep(f'<a href="{href}">{label}</a>')

    text = LINK_RE.sub(link_sub, text)
    text = BOLD_RE.sub(lambda m: f"<strong>{m.group(1)}</strong>", text)
    text = ITALIC_RE.sub(lambda m: f"<em>{m.group(1)}</em>", text)
    return STASH_RE.sub(lambda m: stash[int(m.group(1))], text)


def _split_row(line: str) -> list[str]:
    line = line.strip().replace("\\|", "\x01")
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip().replace("\x01", "|") for c in line.split("|")]


def _parse_aligns(sep_line: str, ncols: int) -> list[str]:
    aligns = []
    for c in _split_row(sep_line):
        left, right = c.startswith(":"), c.endswith(":")
        aligns.append("center" if left and right else "right" if right else "left" if left else "")
    while len(aligns) < ncols:
        aligns.append("")
    return aligns


def _parse_table(lines: list[str], i: int) -> tuple[str, int]:
    header = _split_row(lines[i])
    aligns = _parse_aligns(lines[i + 1], len(header))
    i += 2
    rows = []
    while i < len(lines) and lines[i].strip() and "|" in lines[i]:
        rows.append(_split_row(lines[i]))
        i += 1

    def cell(tag: str, text: str, align: str) -> str:
        attr = f' align="{align}"' if align else ""
        return f"<{tag}{attr}>{_inline(text)}</{tag}>"

    thead = "<thead><tr>" + "".join(
        cell("th", h, aligns[j]) for j, h in enumerate(header)
    ) + "</tr></thead>"
    body = []
    for r in rows:
        r = (r + [""] * len(header))[: len(header)]
        body.append("<tr>" + "".join(cell("td", c, aligns[j]) for j, c in enumerate(r)) + "</tr>")
    return f"<table>{thead}<tbody>{''.join(body)}</tbody></table>", i


def _parse_list(lines: list[str], i: int) -> tuple[str, int]:
    first = LIST_ITEM_RE.match(lines[i])
    base = len(first.group("indent"))
    ordered = first.group("marker")[0].isdigit()
    items: list[dict] = []
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            break
        m = LIST_ITEM_RE.match(line)
        if m:
            if len(m.group("indent")) <= base:
                items.append({"text": m.group("text").strip(), "sub": [], "sub_ordered": None})
            else:
                # One nesting level: anything deeper folds into this level too.
                if not items:
                    items.append({"text": "", "sub": [], "sub_ordered": None})
                it = items[-1]
                if it["sub_ordered"] is None:
                    it["sub_ordered"] = m.group("marker")[0].isdigit()
                it["sub"].append(m.group("text").strip())
            i += 1
            continue
        if line.startswith(" ") and items:
            # Indented continuation line joins the most recent item text.
            it = items[-1]
            if it["sub"]:
                it["sub"][-1] += " " + line.strip()
            else:
                it["text"] += " " + line.strip()
            i += 1
            continue
        break
    parts = []
    for it in items:
        body = _inline(it["text"])
        if it["sub"]:
            sub_tag = "ol" if it["sub_ordered"] else "ul"
            body += f"<{sub_tag}>" + "".join(f"<li>{_inline(t)}</li>" for t in it["sub"]) + f"</{sub_tag}>"
        parts.append(f"<li>{body}</li>")
    tag = "ol" if ordered else "ul"
    return f"<{tag}>" + "".join(parts) + f"</{tag}>", i


def convert(md: str) -> str:
    """Convert subset markdown to HTML. Escape-first; see module docstring."""
    lines = md.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    para: list[str] = []
    i, n = 0, len(lines)

    def flush_para() -> None:
        if para:
            out.append(f"<p>{_inline(chr(10).join(para))}</p>")
            para.clear()

    while i < n:
        line = lines[i]
        if not line.strip():
            flush_para()
            i += 1
            continue
        m = FENCE_RE.match(line)
        if m:
            flush_para()
            fence, lang = m.group(1), m.group(2)
            buf: list[str] = []
            i += 1
            while i < n:
                s = lines[i].strip()
                if s and set(s) == {fence[0]} and len(s) >= len(fence):
                    i += 1
                    break
                buf.append(lines[i])
                i += 1
            cls = f' class="language-{html.escape(lang)}"' if lang else ""
            out.append(f"<pre><code{cls}>{html.escape(chr(10).join(buf))}</code></pre>")
            continue
        if HR_RE.match(line):
            flush_para()
            out.append("<hr>")
            i += 1
            continue
        if QUOTE_RE.match(line):
            flush_para()
            buf = []
            while i < n and QUOTE_RE.match(lines[i]):
                buf.append(QUOTE_RE.match(lines[i]).group(1))
                i += 1
            out.append(f"<blockquote>{convert(chr(10).join(buf))}</blockquote>")
            continue
        if LIST_ITEM_RE.match(line):
            flush_para()
            block, i = _parse_list(lines, i)
            out.append(block)
            continue
        if "|" in line and i + 1 < n and TABLE_SEP_RE.match(lines[i + 1]):
            flush_para()
            block, i = _parse_table(lines, i)
            out.append(block)
            continue
        para.append(line.strip())
        i += 1
    flush_para()
    return "\n".join(out)


def _selftest() -> None:
    cases: list[tuple[str, str]] = [
        ("hello world", "<p>hello world</p>"),
        ("a **bold** and *em* word", "<p>a <strong>bold</strong> and <em>em</em> word</p>"),
        ("use `x < 1` here", "<p>use <code>x &lt; 1</code> here</p>"),
        ("see [docs](https://example.com)", '<p>see <a href="https://example.com">docs</a></p>'),
        ("bad [x](javascript:alert(1))", "<p>bad [x](javascript:alert(1))</p>"),
        ("![logo](img/a.png)", '<p><img src="img/a.png" alt="logo"></p>'),
        ("<script>alert(1)</script>", "<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>"),
        ("<kbd>Ctrl</kbd>", "<p>&lt;kbd&gt;Ctrl&lt;/kbd&gt;</p>"),
        ("---", "<hr>"),
        ("> quoted *text*", "<blockquote><p>quoted <em>text</em></p></blockquote>"),
        ("- a\n- b", "<ul><li>a</li><li>b</li></ul>"),
        ("1. a\n2. b", "<ol><li>a</li><li>b</li></ol>"),
        ("- a\n  - a1\n  - a2\n- b", "<ul><li>a<ul><li>a1</li><li>a2</li></ul></li><li>b</li></ul>"),
        (
            "```python\nprint('<hi>')\n```",
            '<pre><code class="language-python">print(&#x27;&lt;hi&gt;&#x27;)</code></pre>',
        ),
        (
            "| h1 | h2 |\n|:---|---:|\n| a | b |",
            '<table><thead><tr><th align="left">h1</th><th align="right">h2</th></tr></thead>'
            '<tbody><tr><td align="left">a</td><td align="right">b</td></tr></tbody></table>',
        ),
        ("para one\ncontinues", "<p>para one\ncontinues</p>"),
        ("one\n\ntwo", "<p>one</p>\n<p>two</p>"),
    ]
    failed = 0
    for src, expected in cases:
        got = convert(src)
        if got != expected:
            failed += 1
            print(f"FAIL\n  src:      {src!r}\n  expected: {expected!r}\n  got:      {got!r}")
    if failed:
        sys.exit(f"{failed}/{len(cases)} selftest case(s) failed")
    print(f"OK — {len(cases)} cases passed")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        sys.stdout.write(convert(sys.stdin.read()))
