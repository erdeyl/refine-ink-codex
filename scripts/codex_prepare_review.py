#!/usr/bin/env python3
"""Prepare a review workspace for Codex-driven paper review.

Runs deterministic phases (conversion + verification), then scaffolds files for
manual multi-pass analysis in Codex.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pdf_to_markdown import EXIT_OK as CONVERT_OK
from pdf_to_markdown import convert_pdf
from verify_conversion import verify as verify_conversion
from verify_references import verify_all


EXIT_OK = 0
EXIT_INPUT_ERROR = 1
EXIT_CONVERSION_ERROR = 2
EXIT_VERIFICATION_FAIL = 3
EXIT_REFERENCE_ERROR = 4
EXIT_IO_ERROR = 5

AGENT_PASSES = [
    "math-logic",
    "notation",
    "exposition",
    "empirical",
    "cross-section",
    "econometrics",
    "literature",
    "references",
    "language",
]

HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$")


def slugify(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return slug or "paper"


def ensure_review_dirs(review_dir: Path) -> None:
    for rel in ["input", "verification", "chunks", "agent_outputs", "output"]:
        (review_dir / rel).mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def summarize_reference_results(results: list[dict[str, Any]]) -> dict[str, int]:
    verified = sum(1 for r in results if r.get("status") == "verified")
    suspicious = sum(1 for r in results if r.get("status") == "suspicious")
    unverifiable = sum(1 for r in results if r.get("status") == "unverifiable")
    return {
        "total": len(results),
        "verified": verified,
        "suspicious": suspicious,
        "unverifiable": unverifiable,
    }


def count_words(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text, flags=re.UNICODE))


def detect_section_tags(heading: str, text: str) -> dict[str, bool]:
    heading_lower = heading.lower()
    return {
        "has_equations": bool(re.search(r"\$|\\\(|\\\[", text)),
        "has_tables": bool(re.search(r"^\s*\|.+\|\s*$", text, flags=re.MULTILINE)),
        "has_figures": bool(re.search(r"!\[|^\s*figure\s+\d+", text, flags=re.IGNORECASE | re.MULTILINE)),
        "is_references": any(token in heading_lower for token in ["references", "bibliography", "irodalom", "hivatkozas"]),
        "is_abstract": "abstract" in heading_lower or "osszefoglalo" in heading_lower,
    }


def build_chunk_map(converted_md_path: Path) -> list[dict[str, Any]]:
    text = converted_md_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    heading_rows: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines, start=1):
        match = HEADING_RE.match(line.strip())
        if match:
            level = len(match.group(1))
            heading = match.group(2).strip()
            heading_rows.append((index, level, heading))

    if not lines:
        return []

    chunks: list[dict[str, Any]] = []
    if not heading_rows:
        section_text = "\n".join(lines)
        tags = detect_section_tags("Document", section_text)
        chunks.append(
            {
                "id": "c1",
                "heading": "Document",
                "level": 0,
                "start_line": 1,
                "end_line": len(lines),
                "words": count_words(section_text),
                **tags,
            }
        )
        return chunks

    starts = heading_rows + [(len(lines) + 1, 0, "")]
    for idx, (start_line, level, heading) in enumerate(heading_rows, start=1):
        next_start = starts[idx][0]
        end_line = max(start_line, next_start - 1)
        section_text = "\n".join(lines[start_line - 1 : end_line])
        tags = detect_section_tags(heading, section_text)
        chunks.append(
            {
                "id": f"c{idx}",
                "heading": heading,
                "level": level,
                "start_line": start_line,
                "end_line": end_line,
                "words": count_words(section_text),
                **tags,
            }
        )

    return chunks


def write_agent_output_stubs(agent_output_dir: Path) -> None:
    for name in AGENT_PASSES:
        path = agent_output_dir / f"{name}.md"
        if path.exists():
            continue
        path.write_text(
            (
                f"# {name} findings\n\n"
                "_No findings yet. Add evidence-grounded findings with severity and confidence._\n"
            ),
            encoding="utf-8",
        )


def review_template(paper_title: str, review_dir: Path, verification_status: str) -> str:
    return f"""# Referee Report

**Manuscript:** {paper_title}
**Review Workspace:** {review_dir}
**Conversion Verification:** {verification_status}
**Date:** {datetime.now().strftime('%Y-%m-%d')}

## Summary

[Write 1-2 paragraphs summarizing the paper.]

## Overall Assessment

[Assess strengths, concerns, and recommendation.]

## Major Comments

1. [Major issue with evidence and correction]

## Minor Comments

1. [Minor issue with precise correction]

## Econometric/Statistical Methodology

[Dedicated methods assessment.]

## Literature and References

[Coverage assessment + reference verification interpretation.]

## Language and Presentation

[Constructive language/presentation suggestions.]

## Suggestions for Improvement

[Optional enhancements.]

## Appendix A: Detailed Findings

| ID | Dimension | Severity | Confidence | Location | Evidence | Correction |
|---|---|---|---|---|---|---|

## Appendix B: Low-Confidence Findings

[List tentative findings below 50% confidence.]
"""


def next_steps_template(review_dir: Path, ref_summary: dict[str, int]) -> str:
    return f"""# Next Steps (Codex)

Review workspace is ready at:

`{review_dir}`

## Deterministic Phase Results

- Conversion + verification completed
- Reference verification completed
- Chunk map generated at `chunks/chunk_map.json`
- References: {ref_summary['verified']} verified, {ref_summary['suspicious']} suspicious, {ref_summary['unverifiable']} unverifiable

## Run qualitative analysis passes

Create/update these files in `agent_outputs/`:

1. `math-logic.md`
2. `notation.md`
3. `exposition.md`
4. `empirical.md`
5. `cross-section.md`
6. `econometrics.md`
7. `literature.md`
8. `references.md`
9. `language.md`

## Synthesize final report

Write final review to:

- `output/review_EN.md`
- Optional Hungarian output: `output/review_HU.md`

Render HTML with:

```bash
python scripts/md_to_html.py {review_dir}/output/review_EN.md
```

## Evidence discipline

- Quote exact source text from `input/original_converted.md`
- Assign severity and confidence per finding
- Keep unverifiable claims in low-confidence appendix
"""


def prepare_review(args: argparse.Namespace) -> int:
    pdf_path = Path(args.pdf).expanduser().resolve()
    if not pdf_path.is_file() or pdf_path.suffix.lower() != ".pdf":
        print(f"Error: invalid PDF path: {pdf_path}", file=sys.stderr)
        return EXIT_INPUT_ERROR

    reviews_dir = Path(args.reviews_dir).expanduser().resolve()
    reviews_dir.mkdir(parents=True, exist_ok=True)

    paper_slug = slugify(args.name) if args.name else slugify(pdf_path.stem)
    date_tag = datetime.now().strftime("%Y-%m-%d")
    review_dir = reviews_dir / f"{paper_slug}_{date_tag}"

    if review_dir.exists() and not args.force:
        print(
            f"Error: review directory already exists: {review_dir}\n"
            "Use --force to overwrite scaffold files in that directory.",
            file=sys.stderr,
        )
        return EXIT_IO_ERROR

    ensure_review_dirs(review_dir)

    input_dir = review_dir / "input"
    verification_dir = review_dir / "verification"
    chunks_dir = review_dir / "chunks"
    agent_outputs_dir = review_dir / "agent_outputs"
    output_dir = review_dir / "output"

    original_pdf = input_dir / "original.pdf"
    shutil.copy2(pdf_path, original_pdf)

    print(f"[1/5] Converting PDF: {original_pdf}")
    convert_code = convert_pdf(original_pdf, input_dir)
    if convert_code != CONVERT_OK:
        return EXIT_CONVERSION_ERROR

    converted_md = input_dir / "original_converted.md"
    references_json = input_dir / "original_references.json"

    if not converted_md.exists() or not references_json.exists():
        print("Error: expected conversion outputs were not created.", file=sys.stderr)
        return EXIT_CONVERSION_ERROR

    print(f"[2/5] Verifying conversion: {converted_md.name}")
    try:
        conversion_report = verify_conversion(str(original_pdf), str(converted_md))
    except Exception as exc:
        print(f"Error during conversion verification: {exc}", file=sys.stderr)
        return EXIT_VERIFICATION_FAIL

    conversion_report_path = verification_dir / "original_verification.json"
    write_json(conversion_report_path, conversion_report)

    if conversion_report.get("status") == "FAIL":
        print(
            f"Conversion verification failed. See: {conversion_report_path}",
            file=sys.stderr,
        )
        return EXIT_VERIFICATION_FAIL

    print(f"[3/5] Verifying references: {references_json.name}")
    with references_json.open("r", encoding="utf-8") as f:
        references = json.load(f)

    if not isinstance(references, list):
        print("Error: references JSON is not a list.", file=sys.stderr)
        return EXIT_REFERENCE_ERROR

    reference_results: list[dict[str, Any]] = []
    if references and not args.skip_references:
        try:
            s2_api_key = args.s2_api_key or os.environ.get("S2_API_KEY")
            reference_results = asyncio.run(verify_all(references, args.email, s2_api_key))
        except Exception as exc:
            print(f"Error during reference verification: {exc}", file=sys.stderr)
            return EXIT_REFERENCE_ERROR

    reference_report_path = verification_dir / "reference_report.json"
    write_json(reference_report_path, reference_results)
    ref_summary = summarize_reference_results(reference_results)

    print("[4/5] Building chunk map and agent stubs")
    chunk_map = build_chunk_map(converted_md)
    chunk_map_path = chunks_dir / "chunk_map.json"
    write_json(chunk_map_path, chunk_map)
    write_agent_output_stubs(agent_outputs_dir)

    print("[5/5] Writing scaffold outputs")
    review_en_path = output_dir / "review_EN.md"
    review_en_path.write_text(
        review_template(pdf_path.stem, review_dir, conversion_report.get("status", "UNKNOWN")),
        encoding="utf-8",
    )

    next_steps_path = review_dir / "NEXT_STEPS.md"
    next_steps_path.write_text(next_steps_template(review_dir, ref_summary), encoding="utf-8")

    manifest = {
        "version": "codex-1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "paper": {
            "source_pdf": str(pdf_path),
            "workspace_pdf": str(original_pdf),
            "slug": paper_slug,
        },
        "conversion": {
            "status": conversion_report.get("status"),
            "report_path": str(conversion_report_path),
        },
        "chunking": {
            "chunk_map_path": str(chunk_map_path),
            "total_chunks": len(chunk_map),
        },
        "reference_verification": {
            **ref_summary,
            "report_path": str(reference_report_path),
        },
        "outputs": {
            "review_markdown": str(review_en_path),
            "next_steps": str(next_steps_path),
            "agent_outputs": [str(agent_outputs_dir / f"{name}.md") for name in AGENT_PASSES],
        },
    }

    manifest_path = output_dir / "manifest.json"
    write_json(manifest_path, manifest)

    print("\nReview workspace prepared.")
    print(f"  Directory: {review_dir}")
    print(f"  Conversion: {conversion_report.get('status')}")
    print(
        "  References: "
        f"{ref_summary['verified']} verified, "
        f"{ref_summary['suspicious']} suspicious, "
        f"{ref_summary['unverifiable']} unverifiable"
    )
    print(f"  Next steps: {next_steps_path}")
    return EXIT_OK


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a Codex review workspace from an academic PDF.",
    )
    parser.add_argument("pdf", help="Path to input PDF")
    parser.add_argument(
        "--reviews-dir",
        default="reviews",
        help="Root directory for generated review workspaces (default: reviews)",
    )
    parser.add_argument("--name", default=None, help="Optional slug override")
    parser.add_argument(
        "--email",
        default="review@refine-ink.local",
        help="Email for CrossRef/OpenAlex polite pool",
    )
    parser.add_argument("--s2-api-key", default=None, help="Semantic Scholar API key")
    parser.add_argument(
        "--skip-references",
        action="store_true",
        help="Skip API verification of references",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow reuse of existing review directory name",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sys.exit(prepare_review(args))


if __name__ == "__main__":
    main()
