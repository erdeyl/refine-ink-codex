import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import review_consistency_lint as lint


def _ids(report: dict) -> set[str]:
    return {finding["id"] for finding in report["findings"]}


class TestReviewConsistencyLint(unittest.TestCase):
    def test_detects_search_syntax_and_template_artifact(self):
        text = """
        Table 1 Search string
        "digital trade rules" OR "digital trade agreement" AND "development" AND "effect"
        Google Scholar searched anywhere in the article.
        Web of Science used (Topic) fields.
        TITLE-ABS-KEY (digital trade rules) OR TITLE-ABS-KEY (digital trade agreement)
        AND TITLE-ABS-KEY (development) AND TITLE-ABS-KEY (effect)) AND PUBYEAR > 2009
        A total of 1578 articles were found. The patients were screened for exclusion criteria.
        """
        report = lint.lint_markdown(text)
        ids = _ids(report)
        self.assertIn("C12", ids)
        self.assertIn("C22", ids)
        self.assertIn("C34", ids)

    def test_detects_article_only_mismatch_and_definition_gap(self):
        text = """
        RQ1 asks how digital trade rules originated.
        RQ2 asks how digital trade rules shaped networks.
        Exclusion criteria: Research other than articles.
        Burri, M. (2023). Research Handbook on Digital Trade (pp. 9-27). Edward Elgar.
        """
        report = lint.lint_markdown(text)
        ids = _ids(report)
        self.assertIn("C29", ids)
        self.assertIn("C31", ids)

    def test_effect_overclaim_requires_explicit_appraisal(self):
        without_appraisal = """
        This review follows PRISMA.
        Deep rules significantly enhance trade and promote value chain integration.
        """
        report = lint.lint_markdown(without_appraisal)
        self.assertIn("C28", _ids(report))

        with_appraisal = """
        This review follows PRISMA.
        Deep rules significantly enhance trade and promote value chain integration.
        We evaluate risk of bias and perform quality appraisal across studies.
        """
        report_with_appraisal = lint.lint_markdown(with_appraisal)
        self.assertNotIn("C28", _ids(report_with_appraisal))

    def test_detects_terminology_and_cohesion_issues(self):
        text = """
        Among these, the driving role of data-free flow clauses is prominent.
        Cai and Ji test moderation by adding interactive items.
        This deepens the division of the GVC division of labor.
        On the one hand this is a limitation. However, interpretation remains limited.
        Ko (2020) provides a reference for the South Korea-Singapore Digital Partnership Agreement.
        Although American rules promote trade, they may also bring new institutional constraints by narrowing the gap in information and communication technology.
        It has been stagnant for a long time. Later, it gradually transitioned to regional agreements.
        """
        report = lint.lint_markdown(text)
        ids = _ids(report)
        self.assertIn("C16", ids)
        self.assertIn("C19", ids)
        self.assertIn("C25", ids)
        self.assertIn("C24", ids)
        self.assertIn("C26", ids)
        self.assertIn("C35", ids)
        self.assertIn("C36", ids)

    def test_detects_global_overreach_and_network_conflation(self):
        text = """
        Google Scholar returned 48 articles.
        The paper documents a global network pattern and a multi-polar architecture.
        Figure 8 uses VOSviewer keyword co-occurrence mapping.
        """
        report = lint.lint_markdown(text)
        ids = _ids(report)
        self.assertIn("C30", ids)
        self.assertIn("C32", ids)


if __name__ == "__main__":
    unittest.main()
