import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import md_to_html as renderer  # noqa: E402


class MdToHtmlTests(unittest.TestCase):
    def test_sanitize_html_removes_remote_images(self) -> None:
        cleaned = renderer.sanitize_html('<p>x</p><img src="https://attacker.test/pixel" alt="x">')
        self.assertIn("<p>x</p>", cleaned)
        self.assertNotIn("<img", cleaned)

    def test_convert_escapes_title_markup(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            md_path = Path(td) / "review.md"
            md_path.write_text(
                "# <script>alert(1)</script>\n\n**Manuscript:** <b>Danger</b>\n\nBody text.\n",
                encoding="utf-8",
            )
            out_path = Path(td) / "review.html"
            renderer.convert(str(md_path), str(out_path))
            html = out_path.read_text(encoding="utf-8")

        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("Danger", html)


if __name__ == "__main__":
    unittest.main()
