"""Tests for the hero-SVG whitelist sanitizer.

The hero SVG is the one analyst-authored input that is genuine markup, so the
sanitizer is a security boundary: script/style must vanish with their content,
event handlers and style attributes must be dropped, and no URL-carrying
attribute may survive. These tests are deliberately adversarial.

Run from the repo root: python3 -m unittest discover -s tests
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(
    0, str(REPO_ROOT / "skills" / "markdown-to-html-article" / "scripts")
)

import svg_sanitizer  # noqa: E402


class StripsDangerousContentTest(unittest.TestCase):
    def test_script_stripped_with_its_content(self):
        out = svg_sanitizer.sanitize_svg(
            '<svg><script>alert(1)</script><circle r="5"/></svg>'
        )
        self.assertNotIn("alert", out)
        self.assertNotIn("script", out)
        self.assertIn('<circle r="5"/>', out)

    def test_mixed_case_script_stripped(self):
        out = svg_sanitizer.sanitize_svg(
            '<svg><ScRiPt>alert(1)</sCrIpT><rect x="1"/></svg>'
        )
        self.assertNotIn("alert", out)
        self.assertIn('<rect x="1"/>', out)

    def test_style_element_stripped_with_its_content(self):
        out = svg_sanitizer.sanitize_svg("<svg><style>.a{fill:red}</style><g/></svg>")
        self.assertNotIn("fill:red", out)
        self.assertIn("<g/>", out)

    def test_event_handler_attribute_dropped(self):
        out = svg_sanitizer.sanitize_svg('<svg><rect onclick="evil()" x="1"/></svg>')
        self.assertNotIn("onclick", out)
        self.assertNotIn("evil", out)
        self.assertIn('<rect x="1"/>', out)

    def test_style_attribute_dropped(self):
        out = svg_sanitizer.sanitize_svg('<svg><rect style="fill:red" x="1"/></svg>')
        self.assertNotIn("style", out)

    def test_href_never_survives_even_on_allowed_tags(self):
        out = svg_sanitizer.sanitize_svg(
            '<svg><text href="https://evil.example" x="1">hi</text></svg>'
        )
        self.assertNotIn("href", out)
        self.assertIn('<text x="1">hi</text>', out)

    def test_anchor_and_image_tags_dropped_children_kept(self):
        out = svg_sanitizer.sanitize_svg(
            '<svg><a href="https://x.example"><text x="1">hi</text></a>'
            '<image href="https://x.example/a.png"/></svg>'
        )
        self.assertNotIn("<a", out)
        self.assertNotIn("image", out)
        self.assertNotIn("href", out)
        self.assertIn('<text x="1">hi</text>', out)

    def test_unknown_tag_dropped_but_children_kept(self):
        out = svg_sanitizer.sanitize_svg(
            '<svg><foreignObject><rect x="1"/></foreignObject></svg>'
        )
        self.assertNotIn("foreignobject", out.lower())
        self.assertIn('<rect x="1"/>', out)

    def test_attribute_value_quotes_are_escaped(self):
        # A quote inside an attribute value must not terminate the attribute
        # and smuggle in a handler.
        out = svg_sanitizer.sanitize_svg(
            "<svg><rect x='1\" onmouseover=\"evil'/></svg>"
        )
        self.assertIn('<rect x="1&quot; onmouseover=&quot;evil"/>', out)
        self.assertNotIn('onmouseover="evil"', out)


class KeepsWhitelistedContentTest(unittest.TestCase):
    def test_basic_shape_and_presentation_attrs_survive(self):
        out = svg_sanitizer.sanitize_svg(
            '<svg viewBox="0 0 10 10"><rect x="1" fill="#fff"/></svg>'
        )
        self.assertIn('<svg viewbox="0 0 10 10">', out)
        self.assertIn('<rect x="1" fill="#fff"/>', out)

    def test_gradient_defs_survive(self):
        out = svg_sanitizer.sanitize_svg(
            '<svg><defs><linearGradient id="g" x1="0" x2="1">'
            '<stop offset="0" stop-color="#000"/></linearGradient></defs></svg>'
        )
        self.assertIn('<lineargradient id="g" x1="0" x2="1">', out)
        self.assertIn('<stop offset="0" stop-color="#000"/>', out)

    def test_text_content_stays_escaped(self):
        out = svg_sanitizer.sanitize_svg('<svg><text x="1">5 &lt; 9</text></svg>')
        self.assertIn("5 &lt; 9", out)


if __name__ == "__main__":
    unittest.main()
