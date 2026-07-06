"""Tests for the docs-drift mechanical checker.

Each test builds a minimal healthy plugin repo in a temp directory, breaks
exactly one thing, and asserts the matching finding appears (or, for the
healthy fixture, that nothing does). Check functions are exercised directly —
no CLI, no git required.

Run from the repo root: python3 -m unittest discover -s tests
"""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = (
    REPO_ROOT / ".claude" / "skills" / "docs-drift" / "scripts" / "check_docs_drift.py"
)
_spec = importlib.util.spec_from_file_location("check_docs_drift", CHECKER_PATH)
drift = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drift)

DESCRIPTION = "Test plugin description"


def write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_healthy_repo(root):
    """One skill (foo), its command, index, catalog rows, synced manifests."""
    write(root, "skills/foo/SKILL.md", "---\nname: foo\ndescription: does foo\n---\n")
    write(root, "commands/foo.md", "Invoke the `foo` skill.\n")
    write(root, "docs/knowledge/skills/foo-index.md", "# foo\n")
    write(
        root,
        "docs/knowledge/codemap.md",
        "| foo | [skills/foo-index.md](skills/foo-index.md) | does foo |\n",
    )
    write(root, "README.md", "| [foo](./skills/foo/) | does foo |\n| `/foo` | foo |\n")
    write(
        root,
        ".claude-plugin/plugin.json",
        json.dumps({"name": "test-plugin", "description": DESCRIPTION}),
    )
    write(
        root,
        ".claude-plugin/marketplace.json",
        json.dumps(
            {"plugins": [{"name": "test-plugin", "description": DESCRIPTION}]}
        ),
    )


def run_checks(root):
    findings = drift.Findings()
    for check in (
        drift.check_skill_catalog,
        drift.check_command_catalog,
        drift.check_skill_commands,
        drift.check_orphans,
        drift.check_dead_links,
        drift.check_english_only,
        drift.check_manifest_sync,
    ):
        check(str(root), findings)
    return findings


class DriftCheckerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        make_healthy_repo(self.root)

    def assert_finding(self, findings, severity, category, fragment):
        hits = [
            i
            for i in findings.items
            if i["severity"] == severity
            and i["category"] == category
            and fragment in i["message"]
        ]
        self.assertTrue(
            hits,
            "expected a %s/%s finding mentioning %r, got: %r"
            % (severity, category, fragment, findings.items),
        )

    def test_healthy_repo_is_clean(self):
        findings = run_checks(self.root)
        self.assertEqual(findings.items, [])

    def test_missing_index_file_is_an_error(self):
        (self.root / "docs/knowledge/skills/foo-index.md").unlink()
        self.assert_finding(
            run_checks(self.root), drift.ERROR, "skill-catalog", "foo-index.md"
        )

    def test_skill_missing_from_readme_is_an_error(self):
        write(self.root, "README.md", "| `/foo` | foo |\n")
        self.assert_finding(
            run_checks(self.root), drift.ERROR, "skill-catalog", "README"
        )

    def test_skill_missing_from_codemap_is_an_error(self):
        write(self.root, "docs/knowledge/codemap.md", "nothing here\n")
        self.assert_finding(
            run_checks(self.root), drift.ERROR, "skill-catalog", "codemap"
        )

    def test_frontmatter_name_mismatch_is_a_warning(self):
        write(
            self.root,
            "skills/foo/SKILL.md",
            "---\nname: bar\ndescription: does foo\n---\n",
        )
        self.assert_finding(
            run_checks(self.root), drift.WARNING, "skill-catalog", "frontmatter"
        )

    def test_command_missing_from_readme_is_an_error(self):
        write(self.root, "commands/bar.md", "Invoke something.\n")
        self.assert_finding(
            run_checks(self.root), drift.ERROR, "command-catalog", "/bar"
        )

    def test_skill_without_any_command_is_an_error(self):
        (self.root / "commands/foo.md").unlink()
        self.assert_finding(
            run_checks(self.root), drift.ERROR, "skill-command", "foo"
        )

    def test_command_slug_may_differ_from_skill_name(self):
        (self.root / "commands/foo.md").rename(self.root / "commands/run-foo.md")
        write(
            self.root,
            "README.md",
            "| [foo](./skills/foo/) | does foo |\n| `/run-foo` | foo |\n",
        )
        findings = run_checks(self.root)
        self.assertNotIn("skill-command", [i["category"] for i in findings.items])

    def test_orphan_index_is_an_error(self):
        write(self.root, "docs/knowledge/skills/gone-index.md", "# gone\n")
        self.assert_finding(run_checks(self.root), drift.ERROR, "orphan", "gone")

    def test_private_skill_index_is_not_an_orphan(self):
        write(self.root, ".claude/skills/dev/SKILL.md", "---\nname: dev\n---\n")
        write(self.root, "docs/knowledge/skills/dev-index.md", "# dev\n")
        findings = run_checks(self.root)
        self.assertNotIn("orphan", [i["category"] for i in findings.items])

    def test_dead_relative_link_is_an_error(self):
        write(
            self.root,
            "README.md",
            "| [foo](./skills/foo/) | x |\n| `/foo` | x |\n[gone](./missing.md)\n",
        )
        self.assert_finding(
            run_checks(self.root), drift.ERROR, "dead-link", "missing.md"
        )

    def test_placeholder_link_is_skipped(self):
        write(
            self.root,
            "docs/knowledge/example.md",
            "See [the index](skills/<name>-index.md).\n",
        )
        findings = run_checks(self.root)
        self.assertNotIn("dead-link", [i["category"] for i in findings.items])

    def test_cjk_content_is_a_warning(self):
        # CJK chars via escapes so this test file itself stays GR-1 clean.
        write(self.root, "docs/notes.md", "some \u4e2d\u6587 text\n")
        self.assert_finding(
            run_checks(self.root), drift.WARNING, "english-only", "notes.md"
        )

    def test_manifest_description_mismatch_is_an_error(self):
        write(
            self.root,
            ".claude-plugin/marketplace.json",
            json.dumps({"plugins": [{"name": "test-plugin", "description": "other"}]}),
        )
        self.assert_finding(
            run_checks(self.root), drift.ERROR, "manifest-sync", "description"
        )

    def test_manifest_missing_plugin_entry_is_an_error(self):
        write(
            self.root,
            ".claude-plugin/marketplace.json",
            json.dumps({"plugins": [{"name": "other-plugin", "description": "x"}]}),
        )
        self.assert_finding(
            run_checks(self.root), drift.ERROR, "manifest-sync", "test-plugin"
        )

    def test_unparseable_manifest_is_an_error(self):
        write(self.root, ".claude-plugin/marketplace.json", "{not json")
        self.assert_finding(
            run_checks(self.root), drift.ERROR, "manifest-sync", "parse"
        )

    def test_missing_marketplace_file_is_fine(self):
        (self.root / ".claude-plugin/marketplace.json").unlink()
        findings = run_checks(self.root)
        self.assertNotIn("manifest-sync", [i["category"] for i in findings.items])

    def test_version_bump_check_skips_outside_git(self):
        findings = drift.Findings()
        drift.check_version_bump(str(self.root), findings)
        self.assertEqual(findings.items, [])


if __name__ == "__main__":
    unittest.main()
