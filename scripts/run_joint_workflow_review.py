#!/usr/bin/env python3
"""Run three workflow variants, compare outputs, and generate a joint review."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_prepare_review import (
    EXIT_OK,
    notebooklm_question_log_template,
    prepare_review,
    slugify,
)

STATUS_RANK = {"PASS": 2, "WARN": 1, "FAIL": 0}


def _to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_json_or_default(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return load_json(path)


def _run_single_mode(
    pdf_path: Path,
    reviews_dir: Path,
    base_slug: str,
    mode: dict[str, Any],
    email: str,
    skip_references: bool,
    force: bool,
    run_started_at: str,
) -> Path:
    run_name = f"{base_slug}-{mode['name_suffix']}"
    args = argparse.Namespace(
        pdf=str(pdf_path),
        reviews_dir=str(reviews_dir),
        name=run_name,
        email=email,
        skip_references=skip_references,
        force=force,
        chunking=mode["chunking"],
        pdf_native_only=mode["pdf_native_only"],
        run_started_at=run_started_at,
    )

    code = prepare_review(args)
    if code != EXIT_OK:
        raise RuntimeError(f"workflow mode '{mode['label']}' failed with exit code {code}")

    date_tag = datetime.fromisoformat(run_started_at).astimezone().strftime("%Y-%m-%d")
    return reviews_dir / f"{slugify(run_name)}_{date_tag}"


def _extract_mode_summary(mode: dict[str, Any], review_dir: Path) -> dict[str, Any]:
    verification = load_json_or_default(
        review_dir / "verification" / "original_verification.json",
        {"status": "FAIL", "warnings": ["missing conversion report"], "failures": ["missing conversion report"]},
    )
    lint_report = load_json_or_default(
        review_dir / "verification" / "consistency_lint_report.json",
        {"status": "UNKNOWN", "finding_count": 0, "findings": []},
    )
    reference_report = load_json_or_default(
        review_dir / "verification" / "reference_report.json",
        [],
    )
    extracted_refs = load_json_or_default(
        review_dir / "input" / "original_references.json",
        [],
    )

    warnings = verification.get("warnings", [])
    failures = verification.get("failures", [])
    if not isinstance(warnings, list):
        warnings = [str(warnings)]
    if not isinstance(failures, list):
        failures = [str(failures)]
    status = verification.get("status", "UNKNOWN")
    spot_ratio = _to_float_or_none(verification.get("spot_check_hit_ratio"))
    word_diff = _to_float_or_none(verification.get("word_count_diff_pct"))
    refs_extracted = len(extracted_refs) if isinstance(extracted_refs, list) else 0

    ref_verified = sum(1 for r in reference_report if r.get("status") == "verified")
    ref_suspicious = sum(1 for r in reference_report if r.get("status") == "suspicious")
    ref_unverifiable = sum(1 for r in reference_report if r.get("status") == "unverifiable")

    score = STATUS_RANK.get(status, 0) * 100
    if spot_ratio is None:
        score -= 15
    else:
        score += max(0.0, min(1.0, spot_ratio)) * 40
    if word_diff is None:
        score -= 15
    else:
        score -= max(0.0, word_diff) * 2
    score -= len(warnings) * 6
    score -= len(failures) * 20
    score += refs_extracted * 0.2

    return {
        "label": mode["label"],
        "source_mode": "pdf-native-only" if mode["pdf_native_only"] else "markdown-conversion",
        "chunking_mode": mode["chunking"],
        "review_dir": str(review_dir),
        "status": status,
        "word_count_diff_pct": word_diff,
        "spot_check_hit_ratio": spot_ratio,
        "warnings": warnings,
        "failures": failures,
        "references_extracted": refs_extracted,
        "references_verified": ref_verified,
        "references_suspicious": ref_suspicious,
        "references_unverifiable": ref_unverifiable,
        "lint_status": lint_report.get("status"),
        "lint_finding_count": lint_report.get("finding_count", 0),
        "lint_findings": lint_report.get("findings", []),
        "score": round(score, 2),
        "verification": verification,
    }


def _failed_mode_summary(mode: dict[str, Any], error: str) -> dict[str, Any]:
    return {
        "label": mode["label"],
        "source_mode": "pdf-native-only" if mode["pdf_native_only"] else "markdown-conversion",
        "chunking_mode": mode["chunking"],
        "review_dir": None,
        "status": "FAIL",
        "word_count_diff_pct": None,
        "spot_check_hit_ratio": None,
        "warnings": [error],
        "failures": [error],
        "references_extracted": 0,
        "references_verified": 0,
        "references_suspicious": 0,
        "references_unverifiable": 0,
        "lint_status": "UNKNOWN",
        "lint_finding_count": 0,
        "lint_findings": [],
        "score": -100.0,
        "verification": {},
    }


def _select_best_summary(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    if not summaries:
        raise ValueError("no workflow summaries available")
    non_fail = [s for s in summaries if s.get("status") != "FAIL"]
    pool = non_fail if non_fail else summaries
    return max(pool, key=lambda s: float(s.get("score", -1e9)))


def _fmt_metric(value: float | None, precision: int) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{precision}f}"


def _build_consensus(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    finding_index: dict[str, dict[str, Any]] = {}
    for summary in summaries:
        for finding in summary.get("lint_findings", []):
            finding_id = finding.get("id")
            if not finding_id:
                continue
            entry = finding_index.setdefault(
                finding_id,
                {
                    "id": finding_id,
                    "title": finding.get("title", ""),
                    "severity": finding.get("severity", ""),
                    "max_confidence": 0,
                    "present_in": [],
                },
            )
            entry["max_confidence"] = max(entry["max_confidence"], int(finding.get("confidence", 0) or 0))
            if summary["label"] not in entry["present_in"]:
                entry["present_in"].append(summary["label"])

    consensus = [
        item
        for item in finding_index.values()
        if len(item["present_in"]) >= 2
    ]
    consensus.sort(key=lambda x: (-len(x["present_in"]), -x["max_confidence"], x["id"]))
    return consensus


def _comparison_notebooklm_workflow_template(
    comparison_dir: Path,
    pdf_path: Path,
    summaries: list[dict[str, Any]],
) -> str:
    source_lines = [
        f"1. `{pdf_path}`",
        f"2. `{comparison_dir / 'workflow_comparison.md'}`",
        f"3. `{comparison_dir / 'workflow_comparison.json'}`",
        f"4. `{comparison_dir / 'joint_review.md'}`",
    ]

    next_index = len(source_lines) + 1
    for summary in summaries:
        review_dir = summary.get("review_dir")
        if not review_dir:
            continue
        review_path = Path(review_dir)
        source_lines.extend(
            [
                f"{next_index}. `{review_path / 'input' / 'original_converted.md'}` ({summary['label']})",
                f"{next_index + 1}. `{review_path / 'verification' / 'original_verification.json'}` ({summary['label']})",
                f"{next_index + 2}. `{review_path / 'verification' / 'reference_report.json'}` ({summary['label']})",
                f"{next_index + 3}. `{review_path / 'output' / 'manifest.json'}` ({summary['label']})",
            ]
        )
        next_index += 4

    return f"""# NotebookLM Workflow For Joint Review

Use NotebookLM as a grounded comparison layer across workflow modes. Keep the original PDF in the notebook and treat all other workflow artifacts as derivative evidence to challenge, not to trust blindly.

## Source Pack

{chr(10).join(source_lines)}

## Phase 1: Mode Selection

Ask NotebookLM MCP:

- "Which workflow preserved the paper's title, abstract, section boundaries, tables, and references best?"
- "Where do the workflow outputs disagree about what the paper actually says?"
- "Which verification warnings matter most for selecting the primary workflow?"

## Phase 2: Contradiction Detection

Ask:

- "Which findings or summaries in the comparison artifacts are contradicted by the original PDF?"
- "Which claims appear in one mode only and lack direct support from the PDF?"
- "Which sections are consistently represented across all workflow modes?"

## Phase 3: Final Joint Synthesis QA

Before accepting `joint_review.md`, ask:

- "Which criticisms are strongest across multiple workflow modes and best supported by citations?"
- "Which final recommendations overreach beyond the notebook sources?"
- "What unresolved conversion uncertainties should remain explicit in the final review?"

## Logging Discipline

Record material comparison-stage NotebookLM exchanges in `notebooklm/QUESTION_LOG.md`.
"""


def _render_comparison_md(summaries: list[dict[str, Any]], best: dict[str, Any], consensus: list[dict[str, Any]]) -> str:
    lines = [
        "# Workflow Comparison",
        "",
        f"Best mode by objective score: **{best['label']}** (score {best['score']})",
        "NotebookLM comparison prompts: `notebooklm/WORKFLOW.md`",
        "",
        "| Mode | Source | Chunking | Conversion | Word Diff % | Spot Hit | Refs Extracted | Ref Verify (V/S/U) | Lint Findings | Warnings |",
        "|---|---|---|---|---:|---:|---:|---|---:|---:|",
    ]

    for s in summaries:
        lines.append(
            "| "
            f"{s['label']} | {s['source_mode']} | {s['chunking_mode']} | {s['status']} | "
            f"{_fmt_metric(s['word_count_diff_pct'], 2)} | {_fmt_metric(s['spot_check_hit_ratio'], 3)} | "
            f"{s['references_extracted']} | "
            f"{s['references_verified']}/{s['references_suspicious']}/{s['references_unverifiable']} | "
            f"{s['lint_finding_count']} | {len(s['warnings'])} |"
        )

    lines.extend(["", "## Consensus Lint Findings (present in >=2 modes)", ""])
    if not consensus:
        lines.append("No shared lint findings across modes.")
    else:
        lines.append("| ID | Severity | Max Confidence | Present In | Title |")
        lines.append("|---|---|---:|---|---|")
        for item in consensus:
            lines.append(
                f"| {item['id']} | {item['severity']} | {item['max_confidence']} | "
                f"{', '.join(item['present_in'])} | {item['title']} |"
            )

    return "\n".join(lines).strip() + "\n"


def _render_joint_review_md(
    pdf_path: Path,
    summaries: list[dict[str, Any]],
    best: dict[str, Any],
    consensus: list[dict[str, Any]],
) -> str:
    lines = [
        "# Joint Review (3-Mode Synthesis)",
        "",
        f"Source document: `{pdf_path}`",
        "NotebookLM joint-review guide: `notebooklm/WORKFLOW.md`",
        "",
        "## Recommended Primary Workflow",
        "",
        f"Use **{best['label']}** as the base workflow for this manuscript.",
        f"Reason: best score ({best['score']}) with conversion status `{best['status']}` and "
        f"spot-check hit ratio `{_fmt_metric(best.get('spot_check_hit_ratio'), 3)}`.",
        "",
        "## Cross-Mode Quality Checks Against Original PDF",
        "",
    ]

    for s in summaries:
        lines.append(
            f"- `{s['label']}`: status `{s['status']}`, word diff `{_fmt_metric(s['word_count_diff_pct'], 2)}%`, "
            f"spot hit `{_fmt_metric(s['spot_check_hit_ratio'], 3)}`, extracted refs `{s['references_extracted']}`"
        )

    lines.extend(["", "## Shared Findings to Prioritize", ""])
    if not consensus:
        lines.append("No consensus findings; review manually for document-specific issues.")
    else:
        for item in consensus[:20]:
            lines.append(
                f"1. `{item['id']}` ({item['severity']}, confidence {item['max_confidence']}): {item['title']}"
            )

    lines.extend(["", "## Mode-Specific Deltas", ""])
    for s in summaries:
        unique_ids: list[str] = []
        consensus_ids = {c["id"] for c in consensus}
        for finding in s.get("lint_findings", []):
            fid = finding.get("id")
            if fid and fid not in consensus_ids:
                unique_ids.append(fid)
        unique_preview = ", ".join(unique_ids[:10]) if unique_ids else "none"
        lines.append(f"- `{s['label']}` unique lint IDs: {unique_preview}")

    lines.extend(
        [
            "",
            "## Final Joint Recommendation",
            "",
            "Use the primary mode above, then apply consensus findings from all modes before finalizing the report.",
            "Retain any high-confidence unique findings after manual check against `input/original.pdf`.",
        ]
    )

    return "\n".join(lines).strip() + "\n"


def run_all(args: argparse.Namespace) -> Path:
    pdf_path = Path(args.pdf).expanduser().resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    reviews_dir = Path(args.reviews_dir).expanduser().resolve()
    reviews_dir.mkdir(parents=True, exist_ok=True)

    base_slug = slugify(args.name) if args.name else slugify(pdf_path.stem)
    run_started = datetime.now().astimezone()
    run_started_at = run_started.isoformat()
    date_tag = run_started.strftime("%Y-%m-%d")

    mode_specs = [
        {
            "label": "chunked-md",
            "name_suffix": "chunked-md",
            "chunking": "chunked",
            "pdf_native_only": False,
        },
        {
            "label": "no-chunk-md",
            "name_suffix": "no-chunk-md",
            "chunking": "no-chunk",
            "pdf_native_only": False,
        },
        {
            "label": "pdf-native-only",
            "name_suffix": "pdf-native-only",
            "chunking": "pdf",
            "pdf_native_only": True,
        },
    ]

    summaries: list[dict[str, Any]] = []
    for mode in mode_specs:
        try:
            review_dir = _run_single_mode(
                pdf_path=pdf_path,
                reviews_dir=reviews_dir,
                base_slug=base_slug,
                mode=mode,
                email=args.email,
                skip_references=args.skip_references,
                force=args.force,
                run_started_at=run_started_at,
            )
            summaries.append(_extract_mode_summary(mode, review_dir))
        except Exception as exc:
            summaries.append(_failed_mode_summary(mode, str(exc)))

    best = _select_best_summary(summaries)
    consensus = _build_consensus(summaries)

    comparison_dir = reviews_dir / f"{base_slug}-workflow-comparison_{date_tag}"
    comparison_dir.mkdir(parents=True, exist_ok=True)
    notebooklm_dir = comparison_dir / "notebooklm"
    notebooklm_dir.mkdir(parents=True, exist_ok=True)

    comparison_json = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_pdf": str(pdf_path),
        "summaries": summaries,
        "best_mode": best["label"],
        "consensus_findings": consensus,
    }
    (comparison_dir / "workflow_comparison.json").write_text(
        json.dumps(comparison_json, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    (comparison_dir / "workflow_comparison.md").write_text(
        _render_comparison_md(summaries, best, consensus),
        encoding="utf-8",
    )

    (comparison_dir / "joint_review.md").write_text(
        _render_joint_review_md(pdf_path, summaries, best, consensus),
        encoding="utf-8",
    )
    (notebooklm_dir / "WORKFLOW.md").write_text(
        _comparison_notebooklm_workflow_template(comparison_dir, pdf_path, summaries),
        encoding="utf-8",
    )
    (notebooklm_dir / "QUESTION_LOG.md").write_text(
        notebooklm_question_log_template(),
        encoding="utf-8",
    )

    return comparison_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run chunked, no-chunk, and pdf-native workflows, then compare and synthesize.",
    )
    parser.add_argument("pdf", help="Path to input PDF")
    parser.add_argument("--reviews-dir", default="reviews", help="Root review directory")
    parser.add_argument("--name", default=None, help="Base slug override")
    parser.add_argument("--email", default="", help="Email for reference verification polite pools")
    parser.add_argument("--skip-references", action="store_true", help="Skip API reference checks")
    parser.add_argument("--force", action="store_true", help="Allow reusing existing run dirs")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = run_all(args)
    print(f"Joint workflow comparison ready: {out_dir}")


if __name__ == "__main__":
    main()
