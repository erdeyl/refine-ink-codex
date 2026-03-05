#!/usr/bin/env python3
"""review_consistency_lint.py

Rule-based consistency lint for converted academic manuscripts.

Purpose:
- Surface common internal-logic and overclaim issues early in the Codex workflow.
- Catch wording patterns that frequently produce reviewer comments.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def _line_number(lines: list[str], pattern: str, flags: int = re.IGNORECASE) -> int | None:
    rx = re.compile(pattern, flags)
    for idx, line in enumerate(lines, start=1):
        if rx.search(line):
            return idx
    return None


def _add(
    findings: list[dict[str, Any]],
    finding_id: str,
    title: str,
    severity: str,
    confidence: int,
    line: int | None,
    evidence: str,
    recommendation: str,
) -> None:
    findings.append(
        {
            "id": finding_id,
            "title": title,
            "severity": severity,
            "confidence": confidence,
            "line": line,
            "evidence": evidence,
            "recommendation": recommendation,
        }
    )


def lint_markdown(md_text: str) -> dict[str, Any]:
    lines = md_text.splitlines()
    text = md_text
    flat = re.sub(r"\s+", " ", text)
    findings: list[dict[str, Any]] = []

    # C01: scope contradiction: says no cross-country comparisons while using international framing.
    if re.search(r"does not aim to provide cross-country comparisons", flat, re.IGNORECASE):
        if re.search(r"(international context|reference group|across[- ]country|cross[- ]country)", flat, re.IGNORECASE):
            _add(
                findings,
                "C01",
                "Cross-country scope contradiction",
                "Major",
                95,
                _line_number(lines, r"does not aim to provide cross-country comparisons"),
                "Scope limitation conflicts with international/reference-group framing.",
                "Clarify that the paper is comparative but not a comprehensive benchmarking exercise.",
            )

    # C02: paradox wording ambiguity (levels vs dynamics).
    if re.search(r"development.?gender ratio paradox", flat, re.IGNORECASE):
        if re.search(
            r"changes\s+in\s+gender\s+composition\s+do\s+not\s+simply\s+track\s+increases\s+in\s+gdp\s+per\s+capita",
            flat,
            re.IGNORECASE,
        ):
            _add(
                findings,
                "C02",
                "Paradox wording is ambiguous",
                "Major",
                90,
                _line_number(lines, r"do not simply track increases in GDP per capita"),
                "Could be read as denying within-country co-movement.",
                "State explicitly: within-country dynamics are positive, cross-country levels are non-monotonic.",
            )

    # C03: H2 rejection wording mismatch.
    if re.search(r"reject Hypothesis H\s*2", flat, re.IGNORECASE):
        if re.search(r"trends in the share of female physicians.*closely aligned", flat, re.IGNORECASE | re.DOTALL):
            _add(
                findings,
                "C03",
                "H2 rejection rationale may conflict with H2 wording",
                "Major",
                92,
                _line_number(lines, r"reject Hypothesis H\s*2"),
                "Text reports aligned female-share trends while rejecting H2.",
                "Redefine H2 scope explicitly (share-only vs multi-dimensional trajectories).",
            )

    # C04: potentially inaccurate US parity statement.
    if re.search(r"United States and the United Kingdom.*approaching parity by 2023", flat, re.IGNORECASE | re.DOTALL):
        _add(
            findings,
            "C04",
            "US parity claim needs figure-level check",
            "Minor",
            80,
            _line_number(lines, r"United States and the United Kingdom"),
            "US and UK are grouped together for approaching parity by 2023.",
            "Check against plotted series and qualify the US statement if needed.",
        )

    # C05: list/category phrasing ambiguity.
    if re.search(r"public-sector professions,\s*predominantly publicly financed health systems", flat, re.IGNORECASE):
        _add(
            findings,
            "C05",
            "Category/list phrasing is ambiguous",
            "Minor",
            86,
            _line_number(lines, r"public-sector professions,\s*predominantly publicly financed health systems"),
            "Sentence may blur professions and systems in one list slot.",
            "Rewrite with parallel structure and explicit separators.",
        )

    # C06: ambiguous parenthetical for lowest coefficients.
    if re.search(
        r"\(Hungary\s+and\s+Poland\s+show\s+the\s+lowest,\s+but\s+still\s+strong\s+coefficients\)",
        flat,
        re.IGNORECASE,
    ):
        _add(
            findings,
            "C06",
            "Parenthetical may attach to wrong indicator",
            "Minor",
            88,
            _line_number(lines, r"show the lowest, but still strong coefficients"),
            "Nearby sentence references multiple indicators before the parenthetical.",
            "Specify exactly which column/indicator has the lowest coefficients.",
        )

    # C07: "uniformly negative" overclaim with sparse coverage.
    if re.search(r"uniformly\s+negative", flat, re.IGNORECASE):
        if re.search(r"\bN/?A\b", flat, re.IGNORECASE):
            _add(
                findings,
                "C07",
                "Over-strong claim under missing data",
                "Major",
                93,
                _line_number(lines, r"uniformly negative"),
                "Uniform claim coexists with N/A entries in the table.",
                "Qualify as sign pattern in available data, not universal/statistically robust relationship.",
            )

    # C08: sparse-N table interpretation risk.
    sparse_n_lines = [
        (idx, line)
        for idx, line in enumerate(lines, start=1)
        if re.search(r"<br>\s*[0-2](?:\D|$)", line) and "|" in line
    ]
    if sparse_n_lines:
        sample = "; ".join(f"L{idx}" for idx, _ in sparse_n_lines[:4])
        _add(
            findings,
            "C08",
            "Very sparse sample sizes in correlation table",
            "Major",
            94,
            sparse_n_lines[0][0],
            f"Detected low-N cells ({sample}).",
            "Add a coverage matrix and rerun key comparisons on overlapping windows.",
        )

    # C09: abrupt discourse transition marker.
    line_global = _line_number(lines, r"To interpret international differences")
    line_regional = _line_number(lines, r"Regional specificities also include")
    if line_global and line_regional and 0 < (line_regional - line_global) <= 25:
        _add(
            findings,
            "C09",
            "Transition from global to regional argument is abrupt",
            "Minor",
            78,
            line_regional,
            "Additive phrasing ('also include') follows a global framing paragraph.",
            "Add one bridging sentence to signal return to region-specific mechanisms.",
        )

    # C10: wording ambiguity if both terms appear.
    if re.search(r"gender-balanced labour markets", flat, re.IGNORECASE) and re.search(
        r"lower\s*[-–]\s*but\s+more\s+rapidly\s+increasing", flat, re.IGNORECASE
    ):
        _add(
            findings,
            "C10",
            "Balance vs feminization terminology ambiguity",
            "Minor",
            85,
            _line_number(lines, r"gender-balanced labour markets"),
            "Parity language can conflict with female-share increase language.",
            "Distinguish parity (50/50) from feminization (rising female share).",
        )

    # C11: over-strong decline wording for Hungary male-physician density.
    if re.search(r"only in isolated years", flat, re.IGNORECASE):
        _add(
            findings,
            "C11",
            "Potentially overstated decline wording",
            "Minor",
            82,
            _line_number(lines, r"only in isolated years"),
            "Claim strength may exceed what a plotted series visually supports.",
            "Either quantify with exact counts/years or soften to descriptive language.",
        )

    status = "PASS" if not findings else "WARN"
    return {
        "status": status,
        "finding_count": len(findings),
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run rule-based consistency lint on a converted manuscript markdown file."
    )
    parser.add_argument("input_md", type=Path, help="Path to converted markdown file.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path (default: <input_stem>_consistency_lint.json).",
    )
    args = parser.parse_args()

    text = args.input_md.read_text(encoding="utf-8")
    report = lint_markdown(text)
    out = args.output or args.input_md.with_name(f"{args.input_md.stem}_consistency_lint.json")
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
