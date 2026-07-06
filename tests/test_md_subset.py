"""Tests for the escape-first markdown-subset converter.

The converter's load-bearing property is escape-first: every source run is
HTML-escaped before any tag is emitted, so the only markup in the output is
what the module itself generates. These tests pin that invariant down with
adversarial inputs, then cover the supported block/inline subset.

Run from the repo root: python3 -m unittest discover -s tests
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(
    0, str(REPO_ROOT / "skills" / "markdown-to-html-article" / "scripts")
)

import md_subset  # noqa: E402


class EscapeFirstInvariantTest(unittest.TestCase):
    def test_raw_html_renders_as_literal_text(self):
        self.assertEqual(
            md_subset.convert("<script>alert(1)</script>"),
            "<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>",
        )

    def test_raw_tag_inside_prose_is_escaped(self):
        out = md_subset.convert("press <kbd>Ctrl</kbd> now")
        self.assertIn("&lt;kbd&gt;", out)
        self.assertNotIn("<kbd>", out)

    def test_raw_img_with_event_handler_never_survives(self):
        out = md_subset.convert('<img src=x onerror=alert(1)>')
        self.assertNotIn("<img", out)
        self.assertIn("&lt;img", out)

    def test_javascript_href_is_not_linkified(self):
        out = md_subset.convert("[x](javascript:alert(1))")
        self.assertNotIn("<a", out)

    def test_uppercase_scheme_is_not_linkified(self):
        out = md_subset.convert("[x](JavaScript:alert(1))")
        self.assertNotIn("<a", out)

    def test_data_href_is_not_linkified(self):
        out = md_subset.convert("[x](data:text/html;base64,AAAA)")
        self.assertNotIn("<a", out)

    def test_href_cannot_break_out_of_its_attribute(self):
        # The quote in the URL is escaped before the link regex runs, so it
        # cannot terminate the href attribute and smuggle in a handler.
        out = md_subset.convert('see [x](https://e.com/"onmouseover="evil) end')
        self.assertEqual(
            out,
            '<p>see <a href="https://e.com/&quot;onmouseover=&quot;evil">x</a>'
            " end</p>",
        )

    def test_javascript_image_src_is_not_rendered(self):
        out = md_subset.convert("![a](javascript:alert(1))")
        self.assertNotIn("<img", out)

    def test_data_image_src_is_allowed(self):
        out = md_subset.convert("![a](data:image/png;base64,AAAA)")
        self.assertIn('<img src="data:image/png;base64,AAAA" alt="a">', out)

    def test_code_span_content_is_escaped_and_protected(self):
        self.assertEqual(
            md_subset.convert("use `x < [1](y)` here"),
            "<p>use <code>x &lt; [1](y)</code> here</p>",
        )

    def test_fenced_code_block_content_is_escaped(self):
        out = md_subset.convert("```html\n<script>alert(1)</script>\n```")
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", out)
        self.assertNotIn("<script>", out)

    def test_table_cell_content_is_escaped(self):
        out = md_subset.convert("| h |\n|---|\n| <x> |")
        self.assertIn("<td>&lt;x&gt;</td>", out)


class SubsetRenderingTest(unittest.TestCase):
    def test_bold_italic_link(self):
        self.assertEqual(
            md_subset.convert("a **bold** *em* [d](https://e.com)"),
            '<p>a <strong>bold</strong> <em>em</em> <a href="https://e.com">d</a></p>',
        )

    def test_paragraph_split_on_blank_line(self):
        self.assertEqual(md_subset.convert("one\n\ntwo"), "<p>one</p>\n<p>two</p>")

    def test_horizontal_rule(self):
        self.assertEqual(md_subset.convert("---"), "<hr>")

    def test_blockquote_recurses_into_inline_markup(self):
        self.assertEqual(
            md_subset.convert("> quoted *text*"),
            "<blockquote><p>quoted <em>text</em></p></blockquote>",
        )

    def test_unordered_list_with_one_nesting_level(self):
        self.assertEqual(
            md_subset.convert("- a\n  - a1\n  - a2\n- b"),
            "<ul><li>a<ul><li>a1</li><li>a2</li></ul></li><li>b</li></ul>",
        )

    def test_ordered_list(self):
        self.assertEqual(
            md_subset.convert("1. a\n2. b"), "<ol><li>a</li><li>b</li></ol>"
        )

    def test_table_with_alignment(self):
        out = md_subset.convert("| h1 | h2 |\n|:---|---:|\n| a | b |")
        self.assertIn('<th align="left">h1</th>', out)
        self.assertIn('<td align="right">b</td>', out)

    def test_fence_language_class(self):
        out = md_subset.convert("```python\nprint(1)\n```")
        self.assertIn('<pre><code class="language-python">', out)


if __name__ == "__main__":
    unittest.main()
