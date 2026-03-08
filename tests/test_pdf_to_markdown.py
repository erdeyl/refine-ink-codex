import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pdf_to_markdown as converter  # noqa: E402


class PdfToMarkdownReferenceTests(unittest.TestCase):
    def test_find_references_section_handles_bold_heading_and_doi_subheadings(self) -> None:
        md = """## **8 References**

Tang, M., Jiang, L., Mao, Y., & Cao, L. (2025). Does depth matter?
## 103952. [https://doi.org/10.1016/j.irfa.2025.103952](https://doi.org/10.1016/j.irfa.2025.103952)
Ullah, M., Khan, F. U., & Jehan, M. A. (2025). Integrating digital rules.
Zhu, M. (2025). Impact on global value chains.
"""
        ref_section = converter._find_references_section(md)
        self.assertIsNotNone(ref_section)
        self.assertIn("Ullah, M.", ref_section)
        self.assertIn("Zhu, M.", ref_section)

    def test_extract_references_keeps_entries_after_numeric_doi_heading(self) -> None:
        md = """## **8 References**

Tang, M., Jiang, L., Mao, Y., & Cao, L. (2025). Does depth matter?
## 103952. [https://doi.org/10.1016/j.irfa.2025.103952](https://doi.org/10.1016/j.irfa.2025.103952)
Ullah, M., Khan, F. U., & Jehan, M. A. (2025). Integrating digital rules.
Zhu, M. (2025). Impact on global value chains.
"""
        refs = converter.extract_references(md)
        self.assertGreaterEqual(len(refs), 3)
        joined = "\n".join(r["raw_text"] for r in refs)
        self.assertIn("Ullah, M.", joined)
        self.assertIn("Zhu, M.", joined)

    def test_repair_split_doi_removes_intradoi_spaces(self) -> None:
        text = "doi:10.1080/1226508X.2024.238 8514"
        repaired = converter._repair_split_doi(text)
        self.assertIn("10.1080/1226508X.2024.2388514", repaired)

    def test_parse_reference_does_not_duplicate_title_into_journal(self) -> None:
        ref = converter._parse_reference("Smith, J. (2024). *Only One Italic Block*.")
        self.assertEqual(ref["title"], "Only One Italic Block")
        self.assertEqual(ref["journal"], "")


if __name__ == "__main__":
    unittest.main()
