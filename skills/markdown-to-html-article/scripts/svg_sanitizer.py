#!/usr/bin/env python3
"""svg_sanitizer.py — whitelist sanitizer for the analyst-authored hero SVG.

The hero SVG is the one analyst-produced input that is genuine markup, so it
keeps a dedicated sanitizer (everything else is escape-first, see
md_subset.py). Same whitelist as the old bleach-based implementation:
script/style stripped with their content, unknown tags dropped but children
kept, only known-safe presentation attributes pass. No URL-carrying attribute
(href/src/xlink:href) is whitelisted, so external references cannot survive.

Standard library only. Run `python svg_sanitizer.py --selftest` to check it.
"""
from __future__ import annotations

import html
import re
import sys
from html.parser import HTMLParser

_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[\s\S]*?</\1\s*>", re.IGNORECASE)

# Lowercase everywhere: html.parser lowercases tag and attribute names.
ALLOWED_TAGS = {
    "svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline",
    "polygon", "text", "tspan", "defs", "lineargradient", "radialgradient",
    "stop", "title", "desc", "clippath", "mask",
}

_COMMON = {
    "id", "class", "transform", "opacity",
    "fill", "fill-opacity", "fill-rule",
    "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin",
    "stroke-dasharray", "stroke-opacity",
}

ALLOWED_ATTRS = {
    "svg": {"xmlns", "viewbox", "width", "height", "preserveaspectratio", "aria-label", "role"},
    "path": {"d"},
    "rect": {"x", "y", "width", "height", "rx", "ry"},
    "circle": {"cx", "cy", "r"},
    "ellipse": {"cx", "cy", "rx", "ry"},
    "line": {"x1", "y1", "x2", "y2"},
    "polyline": {"points"},
    "polygon": {"points"},
    "text": {"x", "y", "dx", "dy", "text-anchor", "font-family", "font-size",
             "font-weight", "font-style", "letter-spacing"},
    "tspan": {"x", "y", "dx", "dy", "text-anchor", "font-weight"},
    "lineargradient": {"x1", "y1", "x2", "y2", "gradientunits", "gradienttransform"},
    "radialgradient": {"cx", "cy", "r", "fx", "fy", "gradientunits", "gradienttransform"},
    "stop": {"offset", "stop-color", "stop-opacity"},
    "clippath": {"clippathunits"},
    "mask": {"maskunits", "x", "y", "width", "height"},
}


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []

    def _emit_tag(self, tag: str, attrs: list, self_closing: bool) -> None:
        if tag not in ALLOWED_TAGS:
            return
        allowed = _COMMON | ALLOWED_ATTRS.get(tag, set())
        parts = [tag]
        for name, value in attrs:
            if name in allowed:
                parts.append(f'{name}="{html.escape(value or "", quote=True)}"')
        self.out.append("<" + " ".join(parts) + ("/>" if self_closing else ">"))

    def handle_starttag(self, tag, attrs):
        self._emit_tag(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag, attrs):
        self._emit_tag(tag, attrs, self_closing=True)

    def handle_endtag(self, tag):
        if tag in ALLOWED_TAGS:
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        self.out.append(html.escape(data))


def sanitize_svg(svg: str) -> str:
    cleaned = _SCRIPT_STYLE_RE.sub("", svg)
    parser = _Sanitizer()
    parser.feed(cleaned)
    parser.close()
    return "".join(parser.out)


def _selftest() -> None:
    checks = [
        # (input, must_contain, must_not_contain)
        ('<svg viewBox="0 0 10 10"><rect x="1" fill="#fff"/></svg>',
         ['<svg viewbox="0 0 10 10">', '<rect x="1" fill="#fff"/>'], []),
        ('<svg><script>alert(1)</script><circle r="5"/></svg>',
         ['<circle r="5"/>'], ["alert", "script"]),
        ('<svg><style>.a{fill:red}</style><g/></svg>', ["<g/>"], ["style", "fill:red"]),
        ('<svg><rect onclick="evil()" x="1"/></svg>', ['<rect x="1"/>'], ["onclick", "evil"]),
        ('<svg><rect style="fill:red" x="1"/></svg>', ['<rect x="1"/>'], ["style"]),
        ('<svg><a href="https://x.example"><text x="1">hi</text></a></svg>',
         ['<text x="1">hi</text>'], ["href", "<a"]),
        ('<svg><image href="https://x.example/a.png"/></svg>', [], ["image", "href"]),
        ('<svg><text x="1">a &lt; b</text></svg>', ["a &lt; b"], []),
    ]
    failed = 0
    for src, must, must_not in checks:
        got = sanitize_svg(src)
        for frag in must:
            if frag not in got:
                failed += 1
                print(f"FAIL missing {frag!r}\n  src: {src!r}\n  got: {got!r}")
        for frag in must_not:
            if frag in got:
                failed += 1
                print(f"FAIL leaked {frag!r}\n  src: {src!r}\n  got: {got!r}")
    if failed:
        sys.exit(f"{failed} selftest check(s) failed")
    print(f"OK — {len(checks)} cases passed")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        sys.stdout.write(sanitize_svg(sys.stdin.read()))
