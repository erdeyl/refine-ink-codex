import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import codex_prepare_review as prep  # noqa: E402


class CodexPrepareReviewModeTests(unittest.TestCase):
    def test_no_chunk_mode_forces_single_chunk(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            md_path = Path(td) / "doc.md"
            md_path.write_text("## Intro\n\nA paragraph.\n\n## Results\n\nB paragraph.\n", encoding="utf-8")
            chunk_map = prep.build_chunk_map(md_path, chunking_mode="no-chunk")

        self.assertEqual(chunk_map["total_chunks"], 1)
        self.assertEqual(chunk_map["chunks"][0]["id"], "c1")
        self.assertEqual(chunk_map["dimension_assignments"]["notation"], [["c1"]])
        self.assertEqual(chunk_map["dimension_assignments"]["references"], ["c1"])

    def test_pdf_chunk_mode_requires_pdf_path(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            md_path = Path(td) / "doc.md"
            md_path.write_text("Sample", encoding="utf-8")
            with self.assertRaises(ValueError):
                prep.build_chunk_map(md_path, chunking_mode="pdf", pdf_path=None)

    def test_chunked_mode_preserves_preamble_as_first_chunk(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            md_path = Path(td) / "doc.md"
            md_path.write_text(
                "Title line\n\nAbstract text before heading.\n\n## Intro\nBody text.\n",
                encoding="utf-8",
            )
            chunk_map = prep.build_chunk_map(md_path, chunking_mode="chunked")

        self.assertEqual(chunk_map["chunks"][0]["heading"], "Preamble")
        self.assertEqual(chunk_map["chunks"][1]["heading"], "Intro")

    def test_pdf_native_verification_report_shape(self) -> None:
        report = prep.build_pdf_native_verification_report(
            pdf_path=Path("/tmp/a.pdf"),
            extracted_text="## Page 1\n\nabc def\n",
            page_count=3,
            extracted_word_count=2,
            nonempty_pages=1,
        )
        self.assertEqual(report["status"], "WARN")
        self.assertEqual(report["mode"], "pdf-native-only")
        self.assertEqual(report["page_count"], 3)
        self.assertEqual(report["pdf_word_count"], 2)
        self.assertGreaterEqual(len(report["warnings"]), 1)

    def test_pdf_native_verification_report_fails_on_zero_words(self) -> None:
        report = prep.build_pdf_native_verification_report(
            pdf_path=Path("/tmp/a.pdf"),
            extracted_text="## Page 1\n\n\n",
            page_count=1,
            extracted_word_count=0,
            nonempty_pages=0,
        )
        self.assertEqual(report["status"], "FAIL")
        self.assertGreaterEqual(len(report["failures"]), 1)


if __name__ == "__main__":
    unittest.main()
