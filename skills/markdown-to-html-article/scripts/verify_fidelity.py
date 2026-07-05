#!/usr/bin/env python3
"""Verify that an analyst-produced metadata.json faithfully represents its markdown source.

Deterministic checks only — no LLM, no third-party deps. Errors mean the
rewrite lost or altered source content; warnings need human judgment.

Usage:
    python verify_fidelity.py <markdown_path> <metadata_json_path> [--json]

Exit codes:
    0 — clean, or warnings only
    1 — at least one fidelity error
    2 — usage / IO / malformed-metadata error
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})\s*([^\s`]*)\s*$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
URL_RE = re.compile(r"https?://[^\s)\"'>]+")
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
PATH_RE = re.compile(r"(?<![\w/])[\w.-]+(?:/[\w.-]+)+")
NUMBER_RE = re.compile(r"\d+(?:[.,:]\d+)*%?")
# \u escapes (not literal CJK chars) so this file passes the repo's
# english-only check (GR-1): Hiragana/Katakana, CJK ext-A, CJK, Hangul.
CJK_RE = re.compile("[\\u3040-\\u30ff\\u3400-\\u4dbf\\u4e00-\\u9fff\\uac00-\\ud7af]")
RAW_HTML_RE = re.compile(r"</?[a-zA-Z][a-zA-Z0-9-]*(\s[^<>]*)?/?>")


def split_code_blocks(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Split markdown into (prose, fenced code blocks as (lang, content))."""
    prose: list[str] = []
    blocks: list[tuple[str, str]] = []
    fence: str | None = None
    lang = ""
    buf: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if fence is None:
            m = FENCE_RE.match(line)
            if m:
                fence, lang, buf = m.group(1), m.group(2), []
            else:
                prose.append(line)
        else:
            stripped = line.strip()
            if stripped and set(stripped) == {fence[0]} and len(stripped) >= len(fence):
                blocks.append((lang, "\n".join(buf)))
                fence = None
            else:
                buf.append(line)
    if fence is not None:  # unterminated fence — keep what we have
        blocks.append((lang, "\n".join(buf)))
    return "\n".join(prose), blocks


def normalize_code(content: str) -> str:
    lines = [line.rstrip() for line in content.replace("\r\n", "\n").split("\n")]
    return "\n".join(lines).strip("\n")


def parse_headings(prose: str) -> tuple[list[str], list[str]]:
    """Return (all heading texts, H2/H3 heading texts), in source order."""
    all_h: list[str] = []
    h23: list[str] = []
    for line in prose.split("\n"):
        m = HEADING_RE.match(line)
        if m:
            text = m.group(2).strip()
            all_h.append(text)
            if len(m.group(1)) in (2, 3):
                h23.append(text)
    return all_h, h23


def run_checks(source: str, meta: dict) -> tuple[list[dict], list[dict]]:
    errors: list[dict] = []
    warnings: list[dict] = []
    prose, src_blocks = split_code_blocks(source)
    all_headings, h23 = parse_headings(prose)

    sections = meta.get("sections", [])
    section_headings = [s.get("heading", "") for s in sections]
    merged = [h for s in sections for h in s.get("merged_source_headings", [])]
    omitted_map = {
        o.get("heading", ""): o.get("reason", "")
        for o in meta.get("omitted_headings", [])
    }
    accounted = set(section_headings) | set(merged)

    # E1 section-coverage: every source H2/H3 must be accounted for.
    for h in h23:
        if h not in accounted and h not in omitted_map:
            errors.append({
                "check": "section-coverage",
                "detail": f"source heading covered by no section, merged_source_headings, or omitted_headings: {h!r}",
            })
    for h, reason in omitted_map.items():
        warnings.append({
            "check": "declared-omission",
            "detail": f"analyst omitted section {h!r} — reason: {reason or '(none given)'}",
        })

    # E2 fabricated-section: metadata headings must exist in the source.
    known = set(all_headings)
    for label, values in (
        ("section heading", section_headings),
        ("merged_source_headings entry", merged),
        ("omitted_headings entry", list(omitted_map)),
    ):
        for h in values:
            if h and h not in known:
                errors.append({
                    "check": "fabricated-section",
                    "detail": f"{label} not found in source: {h!r}",
                })

    bodies = "\n\n".join(s.get("body_markdown", "") for s in sections)
    _, body_blocks = split_code_blocks(bodies)
    body_block_set = {(lang.strip(), normalize_code(c)) for lang, c in body_blocks}

    # E3 code-block-fidelity: every source code block verbatim in some body.
    for lang, content in src_blocks:
        if (lang.strip(), normalize_code(content)) not in body_block_set:
            first = content.strip().split("\n")[0] if content.strip() else ""
            errors.append({
                "check": "code-block-fidelity",
                "detail": f"source code block (lang={lang or '(none)'}, first line {first!r}) missing or altered in rewritten bodies",
            })

    # E4 quote-in-body: pull quotes must be verbatim in their own section body.
    for s in sections:
        body = s.get("body_markdown", "")
        for q in s.get("pull_quotes", []):
            if q not in body:
                errors.append({
                    "check": "quote-in-body",
                    "detail": f"pull_quote not verbatim in section {s.get('id')!r}: {q[:80]!r}",
                })

    # W1 fact-token-retention: source numbers / inline code / paths / URLs
    # should survive somewhere in the rewritten report. Trailing sentence
    # punctuation on URL/path matches is a tokenizer artifact — strip it.
    haystack = "\n".join(
        [bodies, meta.get("lede", "")] + [s.get("summary", "") for s in sections]
    )
    tokens: set[str] = set()
    tokens.update(t for t in NUMBER_RE.findall(prose) if len(t) >= 2)
    tokens.update(INLINE_CODE_RE.findall(prose))
    tokens.update(
        p.rstrip(".,;:")
        for p in PATH_RE.findall(prose)
        if "." in p or p.count("/") >= 2
    )
    tokens.update(u.rstrip(".,;:") for u in URL_RE.findall(prose))
    for t in sorted(tokens):
        if t not in haystack:
            warnings.append({
                "check": "fact-token-retention",
                "detail": f"source token missing from rewritten report: {t!r}",
            })

    # W2 language-drift: CJK presence should match between source and rewrite.
    if bodies.strip():
        src_cjk = bool(CJK_RE.search(prose))
        body_cjk = bool(CJK_RE.search(bodies))
        if src_cjk and not body_cjk:
            warnings.append({
                "check": "language-drift",
                "detail": "source contains CJK text but rewritten bodies contain none",
            })
        elif body_cjk and not src_cjk:
            warnings.append({
                "check": "language-drift",
                "detail": "rewritten bodies contain CJK text but source has none",
            })

    # W3 raw-html-in-body: the renderer escapes raw HTML, so any tag the
    # analyst wrote will show up as literal text. Warning, not error —
    # prose like "List<String>" can false-positive; the main agent judges.
    body_prose, _ = split_code_blocks(bodies)
    body_prose = INLINE_CODE_RE.sub("", body_prose)
    for m in {m.group(0) for m in RAW_HTML_RE.finditer(body_prose)}:
        warnings.append({
            "check": "raw-html-in-body",
            "detail": f"likely raw HTML in body_markdown (renders escaped): {m!r}",
        })

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify metadata.json fidelity against its markdown source."
    )
    parser.add_argument("markdown_path")
    parser.add_argument("metadata_json_path")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    try:
        source = Path(args.markdown_path).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"cannot read markdown source: {exc}", file=sys.stderr)
        return 2
    try:
        meta = json.loads(Path(args.metadata_json_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read metadata JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(meta, dict):
        print("metadata JSON must be a single object", file=sys.stderr)
        return 2

    errors, warnings = run_checks(source, meta)
    if args.as_json:
        print(json.dumps({"errors": errors, "warnings": warnings},
                         indent=2, ensure_ascii=False))
    else:
        for e in errors:
            print(f"ERROR [{e['check']}] {e['detail']}")
        for w in warnings:
            print(f"WARN  [{w['check']}] {w['detail']}")
        print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
