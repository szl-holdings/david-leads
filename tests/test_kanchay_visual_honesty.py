# SPDX-License-Identifier: Apache-2.0
"""Lock the public face to KANCHAY tokens, type, and honesty chips."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "app" / "static" / "holo.css").read_text(encoding="utf-8")
JS = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
FONTS = (ROOT / "app" / "static" / "fonts" / "fonts.css").read_text(encoding="utf-8")


class KanchayVisualHonestyTests(unittest.TestCase):
    def test_tokens_and_type_are_kanchay(self):
        self.assertIn("#080c14", CSS)
        self.assertIn("#3af4c8", CSS)
        self.assertIn("#5b8dee", CSS)
        self.assertIn("#d7b96b", CSS)
        self.assertIn('"Space Grotesk"', CSS)
        self.assertIn('"JetBrains Mono"', CSS)
        self.assertIn("font-family: \"Space Grotesk\"", FONTS)
        self.assertIn("font-family: \"JetBrains Mono\"", FONTS)
        self.assertNotIn("Fraunces", CSS)
        self.assertNotIn("Inter", CSS)
        self.assertNotRegex(FONTS, r"url\([^)]*fonts\.googleapis\.com")
        self.assertNotRegex(FONTS, r"url\([^)]*fonts\.gstatic\.com")
        self.assertTrue((ROOT / "app/static/fonts/SpaceGrotesk-Regular.ttf").is_file())
        self.assertTrue((ROOT / "app/static/fonts/JetBrainsMono-Regular.ttf").is_file())
        self.assertFalse((ROOT / "app/static/fonts/inter-400.ttf").exists())
        self.assertFalse((ROOT / "app/static/fonts/fraunces-500.ttf").exists())

    def test_honesty_states_are_visible_and_complete(self):
        for state in ("MEASURED", "REPORTED", "ROADMAP", "UNKNOWN", "SIMULATED", "UNAVAILABLE"):
            with self.subTest(state=state):
                self.assertIn(state, HTML)
                self.assertIn(f"honesty-chip {state.lower()}", HTML)
        self.assertIn("Conjecture 1 (OPEN)", HTML)
        self.assertIn("Never a theorem", HTML)
        self.assertIn("function sourceHonesty(source)", JS)
        self.assertIn('return "ROADMAP"', JS)
        self.assertIn('textContent = "UNKNOWN"', JS)

    def test_empty_states_do_not_fake_a_dashboard(self):
        self.assertIn("honesty-chip unknown", HTML)
        self.assertIn("honesty-chip unavailable", HTML)
        self.assertIn("An unfinished lane is ROADMAP", HTML)
        self.assertIn("This pull returned no organizations", JS)
        self.assertIn("UNKNOWN is not a zero", JS)
        self.assertNotRegex(JS, r'textContent = "--"')
        self.assertNotIn("<span>--</span>", JS)
        self.assertNotIn("empty-orbit", HTML)
        self.assertNotIn("territory-orbit", HTML)
        self.assertNotIn("brief-orbit", HTML)

    def test_does_not_copy_foreign_chrome(self):
        surface = f"{HTML}\n{JS}"
        for banned in (
            "Palantir",
            "Bricklayer",
            "linear.app",
            "Stripe",
            "Vercel",
            "command bar",
            "command-bar",
            "seven-module",
            "7-module",
            "module-rail",
        ):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, surface)

    def test_css_rules_are_balanced(self):
        self.assertEqual(CSS.count("{"), CSS.count("}"))


if __name__ == "__main__":
    unittest.main()
