#!/usr/bin/env python3
"""check_docs_drift.py — detect mechanical "drift" between this plugin's code
and the docs that describe it.

Docs in this repo are hand-maintained: the README "Skills in this plugin" and
"Slash commands" tables, the codemap "Skill indexes" table, the per-skill
`docs/knowledge/skills/<name>-index.md` files, and various relative links.
When a skill or command is added, renamed, or removed, these get out of sync.
This script is the deterministic half of the `docs-drift` skill: it extracts
the ground truth from disk and reports every mechanical mismatch it can prove.

It does NOT judge semantic drift (e.g. "the README sentence no longer
describes what the SKILL.md workflow does") — that needs an LLM and is the
skill's job. This script only reports facts it can check by reading files.

Standard library only — no install step. Runnable as a plain CLI without
Claude, and reused by the Stop hook and (optionally) CI.

CLI:
    python check_docs_drift.py [--root DIR] [--json] [--strict]

Exit codes:
    0  no errors (warnings may still be printed)
    1  one or more errors found
    2  bad usage / cannot locate repo root

With --strict, warnings are also treated as errors (exit 1). Useful in CI.
"""

import argparse
import json
import os
import re
import subprocess
import sys

# --- Severities -------------------------------------------------------------

ERROR = "error"
WARNING = "warning"

# Characters that violate GR-1 (English only): CJK ideographs, Hiragana,
# Katakana, Hangul. Python's re has no \p{Han}, so use explicit ranges.
CJK_RE = re.compile(
    "["
    "\\u3040-\\u30ff"   # Hiragana + Katakana
    "\\u3400-\\u4dbf"   # CJK Extension A
    "\\u4e00-\\u9fff"   # CJK Unified Ideographs
    "\\uf900-\\ufaff"   # CJK Compatibility Ideographs
    "\\uac00-\\ud7af"   # Hangul Syllables
    "]"
)

# Markdown link target capture: the (...) part of [text](target).
LINK_RE = re.compile(r"\]\(([^)]+)\)")

# Text-ish files worth scanning for the English-only rule.
TEXT_EXTS = {".md", ".py", ".sh", ".json", ".css", ".j2", ".txt", ".yml", ".yaml"}

# Directories never scanned (binary/vendored/noise).
SKIP_DIRS = {".git", "__pycache__", "vendor", "node_modules"}

# Functional source dirs — a change here without a version bump is suspicious.
FUNCTIONAL_PREFIXES = ("skills/", "commands/", "agents/", ".claude/hooks/")


class Findings:
    """Accumulator for drift findings, each tagged with a severity."""

    def __init__(self):
        self.items = []

    def add(self, severity, category, message):
        self.items.append(
            {"severity": severity, "category": category, "message": message}
        )

    def error(self, category, message):
        self.add(ERROR, category, message)

    def warn(self, category, message):
        self.add(WARNING, category, message)

    @property
    def errors(self):
        return [i for i in self.items if i["severity"] == ERROR]

    @property
    def warnings(self):
        return [i for i in self.items if i["severity"] == WARNING]


# --- Helpers ----------------------------------------------------------------


def find_root(explicit):
    """Resolve the repo root. Prefer --root, else the git toplevel, else the
    nearest ancestor that has a .claude-plugin/ dir, else cwd."""
    if explicit:
        root = os.path.abspath(explicit)
        if not os.path.isdir(root):
            sys.exit("--root is not a directory: %s" % root)
        return root

    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
        top = out.stdout.strip()
        if top and os.path.isdir(top):
            return top
    except (OSError, subprocess.CalledProcessError):
        pass

    here = os.getcwd()
    cursor = here
    while True:
        if os.path.isdir(os.path.join(cursor, ".claude-plugin")):
            return cursor
        parent = os.path.dirname(cursor)
        if parent == cursor:
            return here
        cursor = parent


def read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def list_dir(path):
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


def _skills_in(skills_dir):
    names = []
    for entry in list_dir(skills_dir):
        skill_path = os.path.join(skills_dir, entry)
        if os.path.isdir(skill_path) and os.path.isfile(
            os.path.join(skill_path, "SKILL.md")
        ):
            names.append(entry)
    return names


def list_skills(root):
    """Exported skill names = subdirs of skills/ that contain a SKILL.md."""
    return _skills_in(os.path.join(root, "skills"))


def list_private_skills(root):
    """Repo-private skill names = subdirs of .claude/skills/ with a SKILL.md.
    These are project-level dev tooling, not exported with the plugin, so they
    are exempt from the README catalog checks."""
    return _skills_in(os.path.join(root, ".claude", "skills"))


def list_commands(root):
    """Command slugs = *.md basenames under commands/."""
    cmd_dir = os.path.join(root, "commands")
    return [
        f[:-3]
        for f in list_dir(cmd_dir)
        if f.endswith(".md") and os.path.isfile(os.path.join(cmd_dir, f))
    ]


def list_index_files(root):
    """Per-skill index names from docs/knowledge/skills/<name>-index.md."""
    idx_dir = os.path.join(root, "docs", "knowledge", "skills")
    names = []
    for f in list_dir(idx_dir):
        if f.endswith("-index.md"):
            names.append(f[: -len("-index.md")])
    return names


def frontmatter_name(skill_md_text):
    """Pull the `name:` value out of YAML frontmatter, if present."""
    if not skill_md_text.startswith("---"):
        return None
    end = skill_md_text.find("\n---", 3)
    block = skill_md_text[3:end] if end != -1 else skill_md_text
    for line in block.splitlines():
        match = re.match(r"\s*name\s*:\s*(.+?)\s*$", line)
        if match:
            return match.group(1).strip().strip("'\"")
    return None


# --- Checks -----------------------------------------------------------------


def check_skill_catalog(root, findings):
    """Every skill on disk must have an index file and be listed in the
    README skills table and the codemap skill-indexes table."""
    readme = read_text(os.path.join(root, "README.md"))
    codemap = read_text(os.path.join(root, "docs", "knowledge", "codemap.md"))
    skills = list_skills(root)

    for name in skills:
        index_path = os.path.join(
            root, "docs", "knowledge", "skills", "%s-index.md" % name
        )
        if not os.path.isfile(index_path):
            findings.error(
                "skill-catalog",
                "skill '%s' has no docs/knowledge/skills/%s-index.md"
                % (name, name),
            )
        if ("skills/%s/" % name) not in readme and (
            "skills/%s)" % name
        ) not in readme:
            findings.error(
                "skill-catalog",
                "skill '%s' is not linked in the README \"Skills in this "
                "plugin\" table (expected a link to skills/%s/)" % (name, name),
            )
        if ("%s-index.md" % name) not in codemap:
            findings.error(
                "skill-catalog",
                "skill '%s' is missing from the codemap \"Skill indexes\" "
                "table (expected skills/%s-index.md)" % (name, name),
            )

        # Frontmatter name should match the directory name.
        fm = frontmatter_name(
            read_text(os.path.join(root, "skills", name, "SKILL.md"))
        )
        if fm and fm != name:
            findings.warn(
                "skill-catalog",
                "skill dir '%s' has frontmatter name '%s' — they should match"
                % (name, fm),
            )


def check_command_catalog(root, findings):
    """Every command file must be listed in the README slash-commands table."""
    readme = read_text(os.path.join(root, "README.md"))
    for slug in list_commands(root):
        if ("/%s" % slug) not in readme:
            findings.error(
                "command-catalog",
                "command '/%s' (commands/%s.md) is not listed in the README "
                "\"Slash commands\" table" % (slug, slug),
            )


def check_orphans(root, findings):
    """Index files / catalog rows that point at skills which no longer exist."""
    skills = set(list_skills(root)) | set(list_private_skills(root))
    for name in list_index_files(root):
        if name not in skills:
            findings.error(
                "orphan",
                "docs/knowledge/skills/%s-index.md has no matching "
                "skills/%s/ or .claude/skills/%s/ directory" % (name, name, name),
            )


def iter_markdown_files(root):
    for base in ("README.md", "AGENTS.md", "CLAUDE.md"):
        p = os.path.join(root, base)
        if os.path.isfile(p):
            yield p
    docs_dir = os.path.join(root, "docs")
    for dirpath, dirnames, filenames in os.walk(docs_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            if f.endswith(".md"):
                yield os.path.join(dirpath, f)


def check_dead_links(root, findings):
    """Relative markdown links whose target file/dir does not exist."""
    for md_path in iter_markdown_files(root):
        base_dir = os.path.dirname(md_path)
        text = read_text(md_path)
        for raw in LINK_RE.findall(text):
            target = raw.strip()
            # Skip external links, anchors, and protocol-relative URLs.
            if (
                target.startswith("#")
                or "://" in target
                or target.startswith("mailto:")
                or target.startswith("//")
            ):
                continue
            # Skip placeholder/template links like skills/<name>-index.md that
            # appear inside example snippets in the docs.
            if "<" in target or ">" in target:
                continue
            # Drop any anchor fragment, then resolve relative to the file.
            target = target.split("#", 1)[0]
            if not target:
                continue
            resolved = os.path.normpath(os.path.join(base_dir, target))
            if not os.path.exists(resolved):
                rel_md = os.path.relpath(md_path, root)
                findings.error(
                    "dead-link",
                    "%s links to '%s' which does not exist" % (rel_md, raw),
                )


def check_english_only(root, findings):
    """GR-1: flag files containing CJK/Kana/Hangul. Warning, since quoting a
    non-English source in quotation marks is an allowed exception."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            ext = os.path.splitext(f)[1].lower()
            if ext not in TEXT_EXTS:
                continue
            path = os.path.join(dirpath, f)
            if CJK_RE.search(read_text(path)):
                findings.warn(
                    "english-only",
                    "%s contains non-English (CJK/Kana/Hangul) characters "
                    "(GR-1) — allowed only as a quoted source"
                    % os.path.relpath(path, root),
                )


def check_version_bump(root, findings):
    """If functional source changed vs HEAD but plugin.json's version line did
    not, warn. Git-gated; silently skips when unavailable."""
    def git(*args):
        try:
            out = subprocess.run(
                ["git", "-C", root, *args],
                capture_output=True, text=True, check=True,
            )
            return out.stdout
        except (OSError, subprocess.CalledProcessError):
            return None

    if git("rev-parse", "--git-dir") is None:
        return
    changed = git("diff", "HEAD", "--name-only")
    if changed is None:
        return
    files = [line.strip() for line in changed.splitlines() if line.strip()]
    if not any(f.startswith(FUNCTIONAL_PREFIXES) for f in files):
        return
    version_diff = git("diff", "HEAD", "--", ".claude-plugin/plugin.json")
    if version_diff is not None and re.search(
        r'^[+-]\s*"version"', version_diff, re.MULTILINE
    ):
        return  # version line was changed — good
    findings.warn(
        "version-bump",
        "functional files changed vs HEAD but .claude-plugin/plugin.json "
        '"version" was not bumped',
    )


# --- Output -----------------------------------------------------------------


def render_human(findings, root):
    lines = []
    if not findings.items:
        lines.append("docs-drift: clean — no drift detected in %s" % root)
        return "\n".join(lines)

    if findings.errors:
        lines.append("docs-drift: %d error(s)" % len(findings.errors))
        for item in findings.errors:
            lines.append("  [ERROR/%s] %s" % (item["category"], item["message"]))
    if findings.warnings:
        lines.append("docs-drift: %d warning(s)" % len(findings.warnings))
        for item in findings.warnings:
            lines.append(
                "  [WARN/%s] %s" % (item["category"], item["message"])
            )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Detect mechanical drift between plugin code and its docs."
    )
    parser.add_argument("--root", help="Repo root. Default: git toplevel / cwd.")
    parser.add_argument(
        "--json", action="store_true", help="Emit findings as JSON."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors (non-zero exit).",
    )
    args = parser.parse_args()

    root = find_root(args.root)
    findings = Findings()

    check_skill_catalog(root, findings)
    check_command_catalog(root, findings)
    check_orphans(root, findings)
    check_dead_links(root, findings)
    check_english_only(root, findings)
    check_version_bump(root, findings)

    if args.json:
        print(
            json.dumps(
                {
                    "root": root,
                    "errors": len(findings.errors),
                    "warnings": len(findings.warnings),
                    "findings": findings.items,
                },
                indent=2,
            )
        )
    else:
        print(render_human(findings, root))

    fail = bool(findings.errors) or (args.strict and bool(findings.warnings))
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
