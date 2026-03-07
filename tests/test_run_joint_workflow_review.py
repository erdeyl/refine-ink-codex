import sys
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_joint_workflow_review as joint  # noqa: E402


class RunJointWorkflowReviewTests(unittest.TestCase):
    def test_failed_mode_summary_marks_failure(self) -> None:
        mode = {"label": "chunked-md", "chunking": "chunked", "pdf_native_only": False}
        summary = joint._failed_mode_summary(mode, "boom")
        self.assertEqual(summary["status"], "FAIL")
        self.assertIsNone(summary["word_count_diff_pct"])
        self.assertIsNone(summary["spot_check_hit_ratio"])
        self.assertEqual(summary["warnings"], ["boom"])

    def test_select_best_prefers_non_fail(self) -> None:
        fail = {"status": "FAIL", "score": 1000.0}
        ok = {"status": "PASS", "score": 10.0}
        best = joint._select_best_summary([fail, ok])
        self.assertIs(best, ok)

    def test_fmt_metric_handles_none(self) -> None:
        self.assertEqual(joint._fmt_metric(None, 2), "n/a")
        self.assertEqual(joint._fmt_metric(1.2345, 2), "1.23")

    def test_render_comparison_handles_missing_metrics(self) -> None:
        summaries = [
            {
                "label": "m1",
                "source_mode": "pdf-native-only",
                "chunking_mode": "pdf",
                "status": "FAIL",
                "word_count_diff_pct": None,
                "spot_check_hit_ratio": None,
                "references_extracted": 0,
                "references_verified": 0,
                "references_suspicious": 0,
                "references_unverifiable": 0,
                "lint_finding_count": 0,
                "warnings": ["x"],
                "score": -10.0,
            }
        ]
        md = joint._render_comparison_md(summaries, summaries[0], [])
        self.assertIn("n/a", md)

    def test_render_joint_review_handles_missing_metrics(self) -> None:
        summary = {
            "label": "m1",
            "status": "FAIL",
            "score": -1.0,
            "spot_check_hit_ratio": None,
            "word_count_diff_pct": None,
            "references_extracted": 0,
            "lint_findings": [],
        }
        md = joint._render_joint_review_md(Path("/tmp/doc.pdf"), [summary], summary, [])
        self.assertIn("n/a", md)

    def test_extract_mode_summary_tolerates_missing_optional_artifacts(self) -> None:
        mode = {"label": "m1", "chunking": "chunked", "pdf_native_only": False}
        with tempfile.TemporaryDirectory() as td:
            review_dir = Path(td)
            (review_dir / "verification").mkdir()
            (review_dir / "verification" / "original_verification.json").write_text(
                json.dumps({"status": "PASS", "warnings": [], "failures": []}),
                encoding="utf-8",
            )
            summary = joint._extract_mode_summary(mode, review_dir)

        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(summary["lint_status"], "UNKNOWN")
        self.assertEqual(summary["references_extracted"], 0)


if __name__ == "__main__":
    unittest.main()
