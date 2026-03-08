import asyncio
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import verify_references as refs  # noqa: E402


class VerifyReferencesTests(unittest.TestCase):
    def test_normalize_doi_value_preserves_structure(self) -> None:
        self.assertNotEqual(
            refs.normalize_doi_value("10.1234/foo-bar"),
            refs.normalize_doi_value("10.1234/foo/bar"),
        )

    def test_build_output_does_not_treat_structurally_different_doi_as_exact(self) -> None:
        ref = {"doi": "10.1234/foo-bar", "title": "A title"}
        match = refs.MatchResult(
            found=True,
            source="crossref",
            title="A title",
            doi="10.1234/foo/bar",
            similarity=1.0,
        )
        output = refs._build_output(0, ref, match, "")
        self.assertEqual(output["status"], "verified")
        self.assertEqual(output["confidence"], 90)
        self.assertNotEqual(output["details"], "Exact DOI match confirmed")

    def test_verify_all_surfaces_worker_errors_as_entries(self) -> None:
        async def boom(*args, **kwargs):
            raise RuntimeError("boom")

        with mock.patch.object(refs, "verify_one", boom):
            results = asyncio.run(refs.verify_all([{"title": "a"}], None, None))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "unverifiable")
        self.assertIn("Verification error: boom", results[0]["details"])

    def test_s2_lookup_handles_null_external_ids(self) -> None:
        class DummyResponse:
            status_code = 200

            def json(self):
                return {"title": "Title", "externalIds": None, "year": 2024}

        async def fake_request(*args, **kwargs):
            return DummyResponse()

        async def runner() -> refs.MatchResult:
            with mock.patch.object(refs, "request_with_backoff", fake_request):
                return await refs.s2_lookup(
                    client=object(),
                    limiter=refs.RateLimiter(1000),
                    ref={"title": "Title", "doi": "10.1234/example"},
                    api_key=None,
                )

        result = asyncio.run(runner())
        self.assertTrue(result.found)
        self.assertEqual(result.doi, "10.1234/example")


if __name__ == "__main__":
    unittest.main()
