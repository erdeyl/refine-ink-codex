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


def _has_any(text: str, patterns: list[str], flags: int = re.IGNORECASE | re.DOTALL) -> bool:
    return any(re.search(pattern, text, flags) for pattern in patterns)


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

    # C12: potential boolean/syntax issue in Scopus query reporting.
    if re.search(r"TITLE-ABS-KEY\s*\(effect\)\)", flat, re.IGNORECASE):
        _add(
            findings,
            "C12",
            "Search query syntax appears malformed",
            "Major",
            95,
            _line_number(lines, r"TITLE-ABS-KEY\s*\(effect\)\)"),
            "Reported query includes an extra closing parenthesis near the Scopus expression.",
            "Report the exact executed query with validated syntax and explicit boolean grouping.",
        )

    # C13: estimator/model taxonomy ambiguity for PPML.
    if _has_any(
        flat,
        [
            r"third category is Poisson Pseudo Maximum Likelihood",
            r"structural gravity model with the PPML method",
        ],
    ):
        _add(
            findings,
            "C13",
            "PPML is mixed with model-class taxonomy",
            "Minor",
            86,
            _line_number(lines, r"Poisson Pseudo Maximum Likelihood"),
            "PPML is presented as a standalone model category while examples describe gravity estimated via PPML.",
            "Separate model families, identification designs, and estimation techniques in the methods taxonomy.",
        )

    # C14: stage-label inconsistency in periodization narrative.
    if _has_any(
        flat,
        [
            r"four stages:\s*early stages,\s*infancy,\s*development,\s*and maturity",
            r"In the early days",
            r"In the early stages",
        ],
    ):
        _add(
            findings,
            "C14",
            "Periodization labels are not used consistently",
            "Minor",
            82,
            _line_number(lines, r"four stages:\s*early stages,\s*infancy,\s*development,\s*and maturity"),
            "Defined stages and section topic sentences use partially overlapping labels.",
            "Use the same stage names consistently in headings and narrative transitions.",
        )

    # C15: citation appears across conflicting stage classifications.
    if _has_any(flat, [r"Centralization.*Elsig\s*&\s*Klotz,\s*2022", r"Maturity.*Elsig\s*&\s*Klotz,\s*2022"]):
        _add(
            findings,
            "C15",
            "Stage assignment of the same citation is ambiguous",
            "Minor",
            84,
            _line_number(lines, r"Elsig\s*&\s*Klotz,\s*2022"),
            "The same citation is used under different stage labels without explicit assignment logic.",
            "State whether stage assignment reflects study period, mechanism, or narrative placement.",
        )

    # C16: likely terminology inversion for data-flow clauses.
    if re.search(r"data-free flow clauses", flat, re.IGNORECASE):
        _add(
            findings,
            "C16",
            "Terminology likely inverts intended data-flow concept",
            "Major",
            92,
            _line_number(lines, r"data-free flow clauses"),
            "The phrase can be interpreted as 'flow without data' instead of 'free flow of data'.",
            "Use unambiguous terms such as 'free flow of data clauses' or 'cross-border data flow clauses'.",
        )

    # C17: unresolved antecedent in bilateral statement.
    if re.search(r"between the two countries", flat, re.IGNORECASE):
        _add(
            findings,
            "C17",
            "Definite bilateral reference lacks explicit antecedent",
            "Minor",
            76,
            _line_number(lines, r"between the two countries"),
            "The phrase can imply a specific pair not previously named in that paragraph.",
            "Use 'partner countries' or 'country pairs' unless a specific dyad is explicitly introduced.",
        )

    # C18: nonstandard economic term.
    if re.search(r"distribution of regular income", flat, re.IGNORECASE):
        _add(
            findings,
            "C18",
            "Nonstandard term may obscure intended welfare concept",
            "Minor",
            90,
            _line_number(lines, r"distribution of regular income"),
            "The phrase is uncommon in this context and may be a translation artifact.",
            "Replace with a specific concept such as value-added distribution, welfare gains, or benefit distribution.",
        )

    # C19: nonstandard econometric wording.
    if re.search(r"interactive items", flat, re.IGNORECASE):
        _add(
            findings,
            "C19",
            "Interaction-term terminology is imprecise",
            "Minor",
            88,
            _line_number(lines, r"interactive items"),
            "The phrase is likely intended to describe interaction terms/effects in moderation analysis.",
            "Use standard wording such as 'interaction terms' or 'interaction effects'.",
        )

    # C20: chronological phrasing mismatch in report-year claim.
    if re.search(r"Report 2025 indicates.*expected to increase.*to .*2024", flat, re.IGNORECASE):
        _add(
            findings,
            "C20",
            "Chronology in report-year statement is unclear",
            "Minor",
            80,
            _line_number(lines, r"Report 2025 indicates"),
            "A 2025 report is cited for a statement phrased as an expectation about 2024.",
            "Clarify whether 2024 is forecast, estimate, or observed value and include full source metadata.",
        )

    # C21: unresolved deictic phrase in methods narrative.
    if re.search(r"these mechanisms", flat, re.IGNORECASE):
        _add(
            findings,
            "C21",
            "Unclear antecedent for 'these mechanisms'",
            "Minor",
            72,
            _line_number(lines, r"these mechanisms"),
            "The expression appears before a concrete mechanism list is fully anchored.",
            "Name the mechanism family explicitly where first introduced.",
        )

    # C22: common template artifact from medical review language.
    if re.search(r"The patients were screened", flat, re.IGNORECASE):
        _add(
            findings,
            "C22",
            "Template artifact: non-document unit in screening section",
            "Major",
            99,
            _line_number(lines, r"The patients were screened"),
            "Screening units are articles/records, not patients.",
            "Replace with 'records were screened' or equivalent PRISMA terminology.",
        )

    # C23: likely moderation wording drift.
    if re.search(r"financial development may play a regulatory role", flat, re.IGNORECASE):
        _add(
            findings,
            "C23",
            "Regulatory vs moderating role terminology is ambiguous",
            "Minor",
            85,
            _line_number(lines, r"financial development may play a regulatory role"),
            "In methods context, 'regulatory role' can be read as policy regulation rather than moderation.",
            "Use 'moderating role/effect' when referring to interaction-based empirical analysis.",
        )

    # C24: connector mismatch in limitations paragraph.
    if (
        re.search(r"On the one hand", flat, re.IGNORECASE)
        and re.search(r"On the other hand", flat, re.IGNORECASE) is None
        and re.search(r"On the one hand.{0,240}However", flat, re.IGNORECASE | re.DOTALL)
    ):
        _add(
            findings,
            "C24",
            "Limitation paragraph uses disjointed connectors",
            "Minor",
            83,
            _line_number(lines, r"On the one hand"),
            "Contrastive markers are used without a clear paired structure.",
            "Use parallel connector structure or list limitations directly without contrastive markers.",
        )

    # C25: redundant phrase in GVC mechanism sentence.
    if re.search(r"division of the GVC division of labor", flat, re.IGNORECASE):
        _add(
            findings,
            "C25",
            "Redundant wording in GVC mechanism statement",
            "Minor",
            96,
            _line_number(lines, r"division of the GVC division of labor"),
            "The phrase duplicates 'division' and reduces readability.",
            "Rewrite as 'deepening GVC specialization' or equivalent precise wording.",
        )

    # C26: unclear contribution phrasing in comparative-study statement.
    if re.search(r"provides a reference for the .*Digital Partnership Agreement", flat, re.IGNORECASE):
        _add(
            findings,
            "C26",
            "Contribution phrasing is imprecise",
            "Minor",
            78,
            _line_number(lines, r"provides a reference for"),
            "The phrase can imply documentary authority rather than analytical implication.",
            "Use 'offers implications for' or 'provides analytical insight for' in comparative-method context.",
        )

    # C27: contrastive marker weakens section transition.
    if re.search(r"no longer limited to .* However, it has evolved", flat, re.IGNORECASE):
        _add(
            findings,
            "C27",
            "Contrastive transition is likely unnecessary",
            "Minor",
            77,
            _line_number(lines, r"no longer limited to"),
            "The transition describes progression, but uses a contrastive connector.",
            "Use a progressive connector (or no connector) to improve logical flow.",
        )

    # C28: strong effect synthesis without explicit evidence appraisal framework.
    has_prisma = re.search(r"\bPRISMA\b", flat, re.IGNORECASE) is not None
    has_strong_effect_language = _has_any(
        flat,
        [
            r"\bsignificant(?:ly)?\b",
            r"\bpromote(?:s|d)?\b",
            r"\benhance(?:s|d)?\b",
            r"\beffectively reduce\b",
            r"\bplayed a crucial role\b",
        ],
    )
    has_appraisal_framework = _has_any(
        flat,
        [
            r"risk of bias",
            r"quality appraisal",
            r"quality assessment",
            r"evidence grading",
            r"identification strategy",
            r"endogeneity",
            r"study quality",
        ],
    )
    if has_prisma and has_strong_effect_language and not has_appraisal_framework:
        _add(
            findings,
            "C28",
            "Effect synthesis lacks explicit appraisal framework",
            "Major",
            89,
            _line_number(lines, r"PRISMA"),
            "Directional effect claims are aggregated without documented quality/risk-of-bias grading.",
            "Add an evidence-appraisal framework and tie synthesis strength to study-level evidentiary quality.",
        )

    # C29: article-only eligibility conflicts with non-article sample markers.
    has_article_only_exclusion = re.search(r"Research other than articles", flat, re.IGNORECASE) is not None
    has_non_article_markers = _has_any(
        flat,
        [
            r"Handbook",
            r"\(pp\.\s*\d+\s*[-–]\s*\d+\)",
            r"Cambridge University Press",
            r"Springer",
            r"Research Paper",
            r"World Economy Brief",
            r"Heinrich-B[öo]ll",
        ],
    )
    if has_article_only_exclusion and has_non_article_markers:
        _add(
            findings,
            "C29",
            "Eligibility rule conflicts with realized corpus composition",
            "Major",
            96,
            _line_number(lines, r"Research other than articles"),
            "The review states non-article exclusion but includes clear non-journal source markers.",
            "Either broaden eligibility criteria explicitly or enforce article-only inclusion consistently.",
        )

    # C30: global inference likely overreaches a heavily single-source corpus.
    if re.search(r"Google Scholar returned\s*48", flat, re.IGNORECASE) and _has_any(
        flat,
        [
            r"global network",
            r"global governance",
            r"multi-?polar",
            r"global digital trade",
        ],
    ):
        _add(
            findings,
            "C30",
            "Global inference may overreach skewed retrieval base",
            "Major",
            84,
            _line_number(lines, r"Google Scholar returned\s*48"),
            "The corpus is highly concentrated in one database while conclusions are framed as global.",
            "Calibrate inference scope to corpus composition or rebalance retrieval strategy.",
        )

    # C31: operational definition gap for key construct in multi-RQ review.
    if (
        re.search(r"digital trade rules", flat, re.IGNORECASE)
        and re.search(r"\bRQ1\b", flat, re.IGNORECASE)
        and re.search(r"\bRQ2\b", flat, re.IGNORECASE)
        and re.search(r"digital trade rules.{0,160}\bdefined as\b", flat, re.IGNORECASE | re.DOTALL) is None
    ):
        _add(
            findings,
            "C31",
            "Operational definition for core construct appears underspecified",
            "Major",
            78,
            _line_number(lines, r"RQ1"),
            "The review spans multiple rule families but does not clearly state a bounded definition pattern.",
            "Define the unit of analysis and hierarchy of rule families before RQ synthesis.",
        )

    # C32: keyword-network evidence may be conflated with geopolitical network claims.
    if _has_any(flat, [r"VOSviewer", r"keyword co-occurrence"]) and _has_any(
        flat,
        [r"U\.S\.-centered", r"multi-centered", r"network pattern"],
    ):
        _add(
            findings,
            "C32",
            "Keyword network may be conflated with rule-diffusion network",
            "Major",
            80,
            _line_number(lines, r"VOSviewer"),
            "Term co-occurrence maps and geopolitical rule-diffusion claims are distinct evidentiary objects.",
            "Explicitly separate bibliometric term-network evidence from institutional/geopolitical network claims.",
        )

    # C33: coding-protocol transparency gap in systematic synthesis.
    if re.search(r"coded the selected literature individually", flat, re.IGNORECASE) and _has_any(
        flat,
        [r"codebook", r"coding protocol", r"inter-rater", r"cross-check", r"double-cod"],
    ) is False:
        _add(
            findings,
            "C33",
            "Coding protocol is underspecified for reproducible synthesis",
            "Major",
            87,
            _line_number(lines, r"coded the selected literature individually"),
            "Coding is mentioned, but extraction forms and coder-consistency procedures are not documented.",
            "Add coding rulebook details, assignment criteria, and coder-consistency procedure reporting.",
        )

    # C34: inconsistent field-scope mechanics across databases.
    if _has_any(flat, [r"anywhere in the article", r"TITLE-ABS-KEY", r"\(Topic\)"]):
        _add(
            findings,
            "C34",
            "Database field scopes appear inconsistent",
            "Major",
            90,
            _line_number(lines, r"anywhere in the article|TITLE-ABS-KEY|\(Topic\)"),
            "Search protocol mixes broad full-text-like scope with title/abstract/topic-constrained scopes.",
            "Harmonize field restrictions across databases or explicitly justify asymmetry and its implications.",
        )

    # C35: ambiguous mechanism statement around ICT-gap narrowing.
    if re.search(
        r"constraints by narrowing the gap in information and communication technology",
        flat,
        re.IGNORECASE,
    ):
        _add(
            findings,
            "C35",
            "Mechanism wording is logically ambiguous",
            "Minor",
            84,
            _line_number(lines, r"narrowing the gap in information and communication technology"),
            "The sentence links narrowing a gap to stronger constraints without clarifying the mechanism.",
            "Specify the gap definition and causal pathway (e.g., harmonization, compliance burden, policy-space loss).",
        )

    # C36: tense/aspect inconsistency in staged-evolution summary.
    if re.search(r"has been stagnant.*Later, it gradually transitioned", flat, re.IGNORECASE):
        _add(
            findings,
            "C36",
            "Tense/aspect shift blurs chronology in stage summary",
            "Minor",
            79,
            _line_number(lines, r"has been stagnant"),
            "Present-perfect and simple-past are mixed in a way that obscures whether stagnation is ongoing or prior-phase.",
            "Align tense/aspect consistently across stage descriptions.",
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
