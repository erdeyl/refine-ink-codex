import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import verify_conversion as verify  # noqa: E402


class VerifyConversionMarkdownTests(unittest.TestCase):
    def test_md_references_handles_bold_numbered_heading(self) -> None:
        md = """## **8 References**

Tang, M., Jiang, L., Mao, Y., & Cao, L. (2025). Does depth matter?
## 103952. [https://doi.org/10.1016/j.irfa.2025.103952](https://doi.org/10.1016/j.irfa.2025.103952)
Ullah, M., Khan, F. U., & Jehan, M. A. (2025). Integrating digital rules.
Wang, Y., & Liu, B. (2025). Services trade effects.
"""
        count = verify.md_references(md)
        self.assertGreaterEqual(count, 3)

    def test_md_table_captions_counts_caption_lines(self) -> None:
        md = """Table 1 Search string
Some explanatory text.
**Table 2:** Inclusion and exclusion criteria
"""
        self.assertEqual(verify.md_table_captions(md), 2)

    def test_md_headings_normalizes_bold_and_number_prefix(self) -> None:
        md = """## **1 Introduction**
## **8 References**
"""
        headings = verify.md_headings(md)
        self.assertIn("introduction", headings)
        self.assertIn("references", headings)

    def test_pdf_references_ignores_inline_mentions(self) -> None:
        text = "Introduction\nFor additional references, see Appendix A.\nNot a bibliography section."
        self.assertEqual(verify.pdf_references(text), 0)

    def test_fuzzy_match_uses_anchor_words_when_first_phrase_differs(self) -> None:
        prefix = " ".join(f"w{i}" for i in range(5000))
        needle = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron"
        near_match = "alfa beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron"
        haystack_words = prefix.split()
        haystack_words[123:138] = near_match.split()
        haystack = " ".join(haystack_words)
        self.assertTrue(verify.fuzzy_match(needle, haystack, threshold=0.85))


if __name__ == "__main__":
    unittest.main()
