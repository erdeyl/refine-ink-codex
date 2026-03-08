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
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure sibling scripts are importable regardless of invocation cwd.
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from pdf_to_markdown import EXIT_OK as CONVERT_OK
from pdf_to_markdown import convert_pdf
from pdf_to_markdown import extract_references_from_pdf
from reference_headings import is_reference_heading_line
from review_consistency_lint import lint_markdown
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
PDF_MAGIC = b"%PDF-"
DEFAULT_PDF_SCAN_EXCLUDES = {".git", ".venv", "venv", "__pycache__", "legacy", "reviews"}
CHUNKING_MODES = {"chunked", "no-chunk", "pdf"}


def slugify(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return slug or "paper"


def ensure_review_dirs(review_dir: Path) -> None:
    for rel in ["input", "verification", "chunks", "agent_outputs", "notebooklm", "output"]:
        (review_dir / rel).mkdir(parents=True, exist_ok=True)


def reset_review_dirs(review_dir: Path) -> None:
    for rel in ["input", "verification", "chunks", "agent_outputs", "notebooklm", "output"]:
        target = review_dir / rel
        if target.exists():
            shutil.rmtree(target)
    for rel in ["NEXT_STEPS.md"]:
        target = review_dir / rel
        if target.exists():
            target.unlink()


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def summarize_reference_results(results: list[dict[str, Any]]) -> dict[str, int]:
    verified = sum(1 for r in results if r.get("status") == "verified")
    suspicious = sum(1 for r in results if r.get("status") == "suspicious")
    unverifiable = sum(1 for r in results if r.get("status") == "unverifiable")
    verification_errors = sum(
        1
        for r in results
        if isinstance(r.get("details"), str) and r["details"].startswith("Verification error:")
    )
    return {
        "total": len(results),
        "verified": verified,
        "suspicious": suspicious,
        "unverifiable": unverifiable,
        "verification_errors": verification_errors,
    }


def summarize_lint_report(report: dict[str, Any]) -> dict[str, Any]:
    finding_count = report.get("finding_count", 0)
    status = report.get("status", "UNKNOWN")
    return {
        "status": status,
        "finding_count": finding_count,
    }


def count_words(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text, flags=re.UNICODE))


def _normalize_match_text(text: str) -> str:
    lowered = text.lower()
    folded = unicodedata.normalize("NFD", lowered)
    return "".join(ch for ch in folded if unicodedata.category(ch) != "Mn")


def _validate_pdf_path(pdf_path: Path) -> None:
    if not pdf_path.exists() or not pdf_path.is_file():
        raise ValueError(f"invalid PDF path: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"path does not end with .pdf: {pdf_path}")
    if not os.access(pdf_path, os.R_OK):
        raise ValueError(f"PDF is not readable: {pdf_path}")
    try:
        with pdf_path.open("rb") as f:
            header = f.read(len(PDF_MAGIC))
    except OSError as exc:
        raise ValueError(f"cannot read PDF header: {exc}") from exc
    if header != PDF_MAGIC:
        raise ValueError(
            f"file does not look like a PDF (missing %PDF- header): {pdf_path}"
        )


def _discover_pdf_candidates(base_dir: Path) -> list[Path]:
    candidates: list[Path] = []
    for entry in sorted(base_dir.iterdir()):
        if entry.name in DEFAULT_PDF_SCAN_EXCLUDES:
            continue
        if entry.is_file() and entry.suffix.lower() == ".pdf":
            candidates.append(entry.resolve())
    return candidates


def resolve_pdf_path(pdf_arg: str | None) -> Path:
    if pdf_arg:
        pdf_path = Path(pdf_arg).expanduser().resolve()
        _validate_pdf_path(pdf_path)
        return pdf_path

    cwd = Path.cwd().resolve()
    candidates = _discover_pdf_candidates(cwd)
    if len(candidates) == 1:
        pdf_path = candidates[0]
        _validate_pdf_path(pdf_path)
        print(f"Auto-detected PDF: {pdf_path}")
        return pdf_path

    if not candidates:
        raise ValueError(
            "no PDF path provided and no candidate PDFs found in current directory; "
            "pass an explicit path, e.g. python scripts/codex_prepare_review.py path/to/paper.pdf"
        )

    listed = "\n".join(f"  - {p}" for p in candidates)
    raise ValueError(
        "multiple PDF candidates found in current directory; pass one explicitly:\n"
        f"{listed}"
    )


def extract_pdf_native_text(pdf_path: Path) -> tuple[str, int, int, int]:
    """Extract plain text directly from PDF pages without Markdown conversion."""
    try:
        import fitz  # pymupdf
    except ImportError as exc:
        raise RuntimeError("pymupdf is required for --pdf-native-only mode") from exc

    doc = fitz.open(str(pdf_path))
    pages: list[str] = []
    total_words = 0
    nonempty_pages = 0
    for idx, page in enumerate(doc, start=1):
        page_text = page.get_text("text").strip()
        page_words = count_words(page_text)
        total_words += page_words
        if page_words > 0:
            nonempty_pages += 1
        pages.append(f"## Page {idx}\n\n{page_text}\n")
    page_count = doc.page_count
    doc.close()

    return "\n\n".join(pages).strip() + "\n", page_count, total_words, nonempty_pages


def build_pdf_native_verification_report(
    pdf_path: Path,
    extracted_text: str,
    page_count: int,
    extracted_word_count: int,
    nonempty_pages: int,
) -> dict[str, Any]:
    """Create a lightweight verification report for PDF-native extraction mode."""
    warnings: list[str] = []
    failures: list[str] = []
    nonempty_ratio = (nonempty_pages / page_count) if page_count > 0 else 0.0

    if extracted_word_count == 0:
        failures.append(
            "PDF-native extraction found no textual content. "
            "The PDF is likely image-only/scanned or extraction failed."
        )
    elif page_count >= 3 and extracted_word_count < 150:
        warnings.append(
            f"Very low extracted text volume for {page_count} pages "
            f"({extracted_word_count} words)."
        )

    if page_count > 0 and nonempty_ratio < 0.5:
        warnings.append(
            f"Only {nonempty_pages}/{page_count} pages yielded text "
            f"({nonempty_ratio:.0%} non-empty pages)."
        )

    if failures:
        status = "FAIL"
    elif warnings:
        status = "WARN"
    else:
        status = "PASS"

    return {
        "status": status,
        "mode": "pdf-native-only",
        "page_count": page_count,
        "nonempty_pages": nonempty_pages,
        "nonempty_page_ratio": round(nonempty_ratio, 3),
        "pdf_word_count": extracted_word_count,
        "md_word_count": None,
        "word_count_diff_pct": None,
        "spot_check_hit_ratio": None,
        "warnings": warnings,
        "failures": failures,
        "notes": [
            "Markdown conversion was skipped; workspace uses direct PDF text extraction.",
            "Metrics are not directly comparable to markdown-conversion mode.",
        ],
        "source_pdf": str(pdf_path),
        "native_markdown_word_count": count_words(extracted_text),
    }


def detect_section_tags(heading: str, text: str) -> dict[str, bool]:
    heading_lower = _normalize_match_text(heading)
    return {
        "has_equations": bool(re.search(r"\$|\\\(|\\\[", text)),
        "has_tables": bool(re.search(r"^\s*\|.+\|\s*$", text, flags=re.MULTILINE)),
        "has_figures": bool(re.search(r"!\[|^\s*figure\s+\d+", text, flags=re.IGNORECASE | re.MULTILINE)),
        "is_references": is_reference_heading_line(heading),
        "is_abstract": "abstract" in heading_lower or "osszefoglalo" in heading_lower,
    }


def _group_chunk_ids(chunk_ids: list[str], group_size: int = 3) -> list[list[str]]:
    if group_size <= 0:
        group_size = 1
    return [chunk_ids[i : i + group_size] for i in range(0, len(chunk_ids), group_size)]


def _heading_contains_any(heading: str, tokens: list[str]) -> bool:
    lowered = _normalize_match_text(heading)
    return any(_normalize_match_text(token) in lowered for token in tokens)


def _build_cross_section_pairs(chunks: list[dict[str, Any]]) -> list[list[str]]:
    by_heading = [(chunk["id"], chunk["heading"]) for chunk in chunks]

    def find_all(tokens: list[str]) -> list[str]:
        return [chunk_id for chunk_id, heading in by_heading if _heading_contains_any(heading, tokens)]

    def unique_pairs(first_ids: list[str], second_ids: list[str]) -> list[list[str]]:
        pairs: list[list[str]] = []
        seen: set[tuple[str, str]] = set()
        for first in first_ids:
            for second in second_ids:
                if not first or not second or first == second:
                    continue
                key = (first, second)
                if key in seen:
                    continue
                seen.add(key)
                pairs.append([first, second])
        return pairs

    pairs: list[list[str]] = []
    intro_ids = find_all(["introduction", "bevezetés", "bevezetes"])
    methods_ids = find_all(["method", "methodology", "identification", "módszertan", "modszertan"])
    results_ids = find_all(["result", "results", "findings", "eredmény", "eredmeny", "eredmények", "eredmenyek"])
    abstract = next((c["id"] for c in chunks if c.get("is_abstract")), None)
    conclusion_ids = find_all(["conclusion", "discussion", "következtetés", "kovetkeztetes"])

    pairs.extend(unique_pairs(intro_ids[:1], results_ids[-2:] if len(results_ids) > 1 else results_ids))
    pairs.extend(unique_pairs(methods_ids[:1], results_ids[-2:] if len(results_ids) > 1 else results_ids))
    if abstract and conclusion_ids:
        pairs.extend(unique_pairs([abstract], conclusion_ids[-1:]))

    if not pairs and len(chunks) >= 2:
        pairs.append([chunks[0]["id"], chunks[-1]["id"]])

    return pairs


def _assign_dimensions(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    chunk_ids = [chunk["id"] for chunk in chunks]
    math_logic = [c["id"] for c in chunks if c.get("has_equations")]
    empirical = [c["id"] for c in chunks if c.get("has_tables") or c.get("has_figures")]
    literature = [
        c["id"]
        for c in chunks
        if _heading_contains_any(
            c["heading"],
            [
                "literature",
                "related work",
                "background",
                "irodalom",
                "elméleti háttér",
                "elmeleti hatter",
            ],
        )
    ]
    references = [c["id"] for c in chunks if c.get("is_references")]
    econometrics = [
        c["id"]
        for c in chunks
        if _heading_contains_any(
            c["heading"],
            ["method", "methodology", "model", "identification", "estimation", "regression"],
        )
    ]

    if not econometrics and empirical:
        econometrics = empirical.copy()

    return {
        "math-logic": math_logic,
        "notation": _group_chunk_ids(chunk_ids, 3),
        "exposition": _group_chunk_ids(chunk_ids, 3),
        "empirical": empirical,
        "cross-section": _build_cross_section_pairs(chunks),
        "econometrics": econometrics,
        "literature": literature,
        "references": references,
        "language": _group_chunk_ids(chunk_ids, 3),
    }


def _single_chunk_assignments(chunk_id: str) -> dict[str, Any]:
    return {
        "math-logic": [chunk_id],
        "notation": [[chunk_id]],
        "exposition": [[chunk_id]],
        "empirical": [chunk_id],
        "cross-section": [[chunk_id]],
        "econometrics": [chunk_id],
        "literature": [chunk_id],
        "references": [chunk_id],
        "language": [[chunk_id]],
    }


def _pdf_chunk_heading(page_text: str, page_num: int) -> str:
    for line in page_text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:120]
    return f"Page {page_num}"


def _build_pdf_chunk_map(pdf_path: Path) -> dict[str, Any]:
    try:
        import fitz  # pymupdf
    except ImportError as exc:
        raise RuntimeError("pymupdf is required for chunking mode 'pdf'") from exc

    doc = fitz.open(str(pdf_path))
    chunks: list[dict[str, Any]] = []
    for page_idx, page in enumerate(doc, start=1):
        page_text = page.get_text("text")
        heading = _pdf_chunk_heading(page_text, page_idx)
        line_count = max(1, len(page_text.splitlines()))
        tags = detect_section_tags(heading, page_text)
        chunks.append(
            {
                "id": f"p{page_idx}",
                "heading": heading,
                "level": 0,
                "page_start": page_idx,
                "page_end": page_idx,
                "start_line": 1,
                "end_line": line_count,
                "words": count_words(page_text),
                **tags,
            }
        )
    doc.close()

    return {
        "total_chunks": len(chunks),
        "chunks": chunks,
        "dimension_assignments": _assign_dimensions(chunks),
    }


def build_chunk_map(
    converted_md_path: Path,
    chunking_mode: str = "chunked",
    pdf_path: Path | None = None,
) -> dict[str, Any]:
    text = converted_md_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    if chunking_mode not in CHUNKING_MODES:
        raise ValueError(f"unsupported chunking mode: {chunking_mode}")

    if chunking_mode == "pdf":
        if pdf_path is None:
            raise ValueError("pdf_path is required for chunking mode 'pdf'")
        return _build_pdf_chunk_map(pdf_path)

    heading_rows: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines, start=1):
        match = HEADING_RE.match(line.strip())
        if match:
            level = len(match.group(1))
            heading = match.group(2).strip()
            heading_rows.append((index, level, heading))

    if not lines:
        return {
            "total_chunks": 0,
            "chunks": [],
            "dimension_assignments": _assign_dimensions([]),
        }

    if chunking_mode == "no-chunk":
        section_text = "\n".join(lines)
        tags = detect_section_tags("Document", section_text)
        single = {
            "id": "c1",
            "heading": "Document",
            "level": 0,
            "start_line": 1,
            "end_line": len(lines),
            "words": count_words(section_text),
            **tags,
        }
        return {
            "total_chunks": 1,
            "chunks": [single],
            "dimension_assignments": _single_chunk_assignments("c1"),
        }

    chunks: list[dict[str, Any]] = []
    if not heading_rows:
        section_text = "\n".join(lines)
        tags = detect_section_tags("Document", section_text)
        single = {
            "id": "c1",
            "heading": "Document",
            "level": 0,
            "start_line": 1,
            "end_line": len(lines),
            "words": count_words(section_text),
            **tags,
        }
        chunks.append(single)
        return {
            "total_chunks": 1,
            "chunks": chunks,
            "dimension_assignments": _assign_dimensions(chunks),
        }

    first_heading_line = heading_rows[0][0]
    preamble_text = "\n".join(lines[: first_heading_line - 1]).strip()
    if preamble_text:
        tags = detect_section_tags("Preamble", preamble_text)
        chunks.append(
            {
                "id": "c1",
                "heading": "Preamble",
                "level": 0,
                "start_line": 1,
                "end_line": first_heading_line - 1,
                "words": count_words(preamble_text),
                **tags,
            }
        )

    starts = heading_rows + [(len(lines) + 1, 0, "")]
    chunk_index_offset = len(chunks)
    for idx, (start_line, level, heading) in enumerate(heading_rows, start=1):
        next_start = starts[idx][0]
        end_line = max(start_line, next_start - 1)
        # start_line/end_line are 1-based; python slicing end is exclusive, so this
        # correctly maps to inclusive end_line.
        section_text = "\n".join(lines[start_line - 1 : end_line])
        tags = detect_section_tags(heading, section_text)
        chunks.append(
            {
                "id": f"c{chunk_index_offset + idx}",
                "heading": heading,
                "level": level,
                "start_line": start_line,
                "end_line": end_line,
                "words": count_words(section_text),
                **tags,
            }
        )

    return {
        "total_chunks": len(chunks),
        "chunks": chunks,
        "dimension_assignments": _assign_dimensions(chunks),
    }


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


def review_template(
    paper_title: str,
    review_dir: Path,
    verification_status: str,
    run_started: datetime,
) -> str:
    return f"""# Referee Report

**Manuscript:** {paper_title}
**Review Workspace:** {review_dir}
**Conversion Verification:** {verification_status}
**Date:** {run_started.astimezone(timezone.utc).strftime('%Y-%m-%d')}

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


def next_steps_template(
    review_dir: Path,
    ref_summary: dict[str, int],
    lint_summary: dict[str, Any],
    source_mode: str,
    chunking_mode: str,
) -> str:
    return f"""# Next Steps (Codex)

Review workspace is ready at:

`{review_dir}`

## Deterministic Phase Results

- Conversion + verification completed
- Reference verification completed
- Source mode: `{source_mode}`
- Chunking mode: `{chunking_mode}`
- Consistency lint: {lint_summary['status']} ({lint_summary['finding_count']} findings)
- Chunk map generated at `chunks/chunk_map.json` (`total_chunks`, `chunks`, `dimension_assignments`)
- References: {ref_summary['verified']} verified, {ref_summary['suspicious']} suspicious, {ref_summary['unverifiable']} unverifiable, {ref_summary['verification_errors']} verification errors

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
- Use `notebooklm/WORKFLOW.md` after preparation, before closing each analysis pass, and again before final synthesis
- Record material NotebookLM MCP interactions in `notebooklm/QUESTION_LOG.md`
- Review `verification/consistency_lint_report.json` and resolve/confirm each flagged issue
- Assign severity and confidence per finding
- Keep unverifiable claims in low-confidence appendix
"""


def notebooklm_workflow_template(review_dir: Path) -> str:
    return f"""# NotebookLM Workflow

Use NotebookLM as a grounded text-analysis sidecar. Treat it as a question-answering and contradiction-detection tool, not as a substitute for quoting the underlying source files.

## Source Pack

Create/update a notebook containing:

1. `{review_dir}/input/original.pdf`
2. `{review_dir}/input/original_converted.md`
3. `{review_dir}/verification/original_verification.json`
4. `{review_dir}/verification/consistency_lint_report.json`
5. `{review_dir}/verification/reference_report.json`
6. `{review_dir}/chunks/chunk_map.json`
7. `agent_outputs/*.md` as soon as you start writing pass outputs

## Phase 1: Grounding After Preparation

Ask NotebookLM MCP:

- "Summarize the paper's research question, identification/design, and main conclusion in five bullets with citations."
- "List any places where the PDF text and converted markdown appear inconsistent or incomplete."
- "Which sections, tables, and figures are central to the paper's main claim?"

## Phase 2: Analysis Pass Support

Use NotebookLM before finalizing each pass:

- `math-logic`: ask for equations, assumptions, and claimed derivation steps that are unsupported or inconsistent.
- `notation`: ask where symbols, abbreviations, or variable names change meaning across sections.
- `exposition`: ask for abstract/introduction/results/conclusion contradictions.
- `empirical`: ask whether textual claims match table and figure evidence.
- `cross-section`: ask for statements in one section that are contradicted or weakened elsewhere.
- `econometrics`: ask for identification threats, missing robustness checks, and interpretation overreach.
- `literature`: ask which cited works are used for framing, method, and evidence, and which obvious comparison points are missing.
- `references`: ask which suspicious or unverifiable references matter materially for the paper's claims.
- `language`: ask for ambiguous, over-strong, or internally inconsistent phrasing with source citations.

## Phase 3: Synthesis QA

Before finalizing `output/review_EN.md`, ask:

- "Which proposed reviewer criticisms are best supported by the source text?"
- "Which of my draft claims are not fully supported by the notebook sources?"
- "What contradictions or overstatements remain unresolved?"

## Phase 4: Workflow Comparison and Final Audit

If you later run `scripts/run_joint_workflow_review.py`, add the comparison workspace outputs to the notebook and ask:

- "Which workflow mode preserved the paper's structure, tables, and references best?"
- "Which claims appear in one workflow's review artifacts but are not supported by the original PDF?"
- "Which unresolved contradictions remain after combining chunked, no-chunk, and PDF-native evidence?"

## Logging Discipline

Record every material NotebookLM exchange in `QUESTION_LOG.md`:

- phase
- question asked
- concise answer summary
- cited source passages/files
- follow-up action in the review
"""


def notebooklm_question_log_template() -> str:
    return """# NotebookLM Question Log

| Phase | Question | Answer Summary | Cited Sources | Follow-up Action |
|---|---|---|---|---|
"""


def prepare_review(args: argparse.Namespace) -> int:
    try:
        pdf_path = resolve_pdf_path(args.pdf)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_INPUT_ERROR

    reviews_dir = Path(args.reviews_dir).expanduser().resolve()
    reviews_dir.mkdir(parents=True, exist_ok=True)

    run_started = getattr(args, "run_started_at", None)
    if isinstance(run_started, str) and run_started:
        run_started_dt = datetime.fromisoformat(run_started).astimezone()
    else:
        run_started_dt = datetime.now().astimezone()

    paper_slug = slugify(args.name) if args.name else slugify(pdf_path.stem)
    date_tag = run_started_dt.strftime("%Y-%m-%d")
    review_dir = reviews_dir / f"{paper_slug}_{date_tag}"

    if review_dir.exists() and not args.force:
        print(
            f"Error: review directory already exists: {review_dir}\n"
            "Use --force to overwrite scaffold files in that directory.",
            file=sys.stderr,
        )
        return EXIT_IO_ERROR
    if review_dir.exists() and args.force:
        reset_review_dirs(review_dir)

    ensure_review_dirs(review_dir)

    input_dir = review_dir / "input"
    verification_dir = review_dir / "verification"
    chunks_dir = review_dir / "chunks"
    agent_outputs_dir = review_dir / "agent_outputs"
    notebooklm_dir = review_dir / "notebooklm"
    output_dir = review_dir / "output"

    original_pdf = input_dir / "original.pdf"
    shutil.copy2(pdf_path, original_pdf)

    source_mode = "pdf-native-only" if args.pdf_native_only else "markdown-conversion"
    chunking_mode = args.chunking
    if chunking_mode not in CHUNKING_MODES:
        print(f"Error: unsupported chunking mode '{chunking_mode}'", file=sys.stderr)
        return EXIT_INPUT_ERROR

    references: list[dict[str, Any]]
    converted_md = input_dir / "original_converted.md"
    references_json = input_dir / "original_references.json"
    conversion_report_path = verification_dir / "original_verification.json"

    if source_mode == "pdf-native-only":
        print(f"[1/5] Extracting PDF text natively: {original_pdf}")
        try:
            native_md_text, page_count, extracted_words, nonempty_pages = extract_pdf_native_text(original_pdf)
        except Exception as exc:
            print(f"Error during PDF-native extraction: {exc}", file=sys.stderr)
            return EXIT_CONVERSION_ERROR

        converted_md.write_text(native_md_text, encoding="utf-8")
        references = extract_references_from_pdf(original_pdf)
        write_json(references_json, references)
        conversion_report = build_pdf_native_verification_report(
            original_pdf,
            native_md_text,
            page_count,
            extracted_words,
            nonempty_pages,
        )
    else:
        print(f"[1/5] Converting PDF: {original_pdf}")
        convert_code = convert_pdf(original_pdf, input_dir)
        if convert_code != CONVERT_OK:
            return EXIT_CONVERSION_ERROR

        if not converted_md.exists() or not references_json.exists():
            print("Error: expected conversion outputs were not created.", file=sys.stderr)
            return EXIT_CONVERSION_ERROR

        print(f"[2/5] Verifying conversion: {converted_md.name}")
        try:
            conversion_report = verify_conversion(str(original_pdf), str(converted_md))
        except Exception as exc:
            print(f"Error during conversion verification: {exc}", file=sys.stderr)
            return EXIT_VERIFICATION_FAIL

        with references_json.open("r", encoding="utf-8") as f:
            loaded_refs = json.load(f)
        if not isinstance(loaded_refs, list):
            print("Error: references JSON is not a list.", file=sys.stderr)
            return EXIT_REFERENCE_ERROR
        references = loaded_refs

    write_json(conversion_report_path, conversion_report)
    if conversion_report.get("status") == "FAIL":
        print(
            f"Conversion verification failed. See: {conversion_report_path}",
            file=sys.stderr,
        )
        return EXIT_VERIFICATION_FAIL

    print(f"[3/5] Verifying references: {references_json.name}")
    reference_results: list[dict[str, Any]] = []
    if references and not args.skip_references:
        try:
            s2_api_key = os.environ.get("S2_API_KEY")
            mailto = args.email.strip() if args.email else None
            if not mailto:
                print(
                    "Warning: --email not provided; CrossRef/OpenAlex polite pool parameters "
                    "will be omitted.",
                    file=sys.stderr,
                )
            reference_results = asyncio.run(verify_all(references, mailto, s2_api_key))
        except Exception as exc:
            print(f"Error during reference verification: {exc}", file=sys.stderr)
            return EXIT_REFERENCE_ERROR

    reference_report_path = verification_dir / "reference_report.json"
    write_json(reference_report_path, reference_results)
    ref_summary = summarize_reference_results(reference_results)

    print("[4/5] Building chunk map, consistency lint, and analysis scaffolds")
    chunk_map = build_chunk_map(converted_md, chunking_mode=chunking_mode, pdf_path=original_pdf)
    chunk_map_path = chunks_dir / "chunk_map.json"
    write_json(chunk_map_path, chunk_map)

    lint_report = lint_markdown(converted_md.read_text(encoding="utf-8"))
    lint_report_path = verification_dir / "consistency_lint_report.json"
    write_json(lint_report_path, lint_report)
    lint_summary = summarize_lint_report(lint_report)

    write_agent_output_stubs(agent_outputs_dir)
    (notebooklm_dir / "WORKFLOW.md").write_text(
        notebooklm_workflow_template(review_dir),
        encoding="utf-8",
    )
    (notebooklm_dir / "QUESTION_LOG.md").write_text(
        notebooklm_question_log_template(),
        encoding="utf-8",
    )

    print("[5/5] Writing output, manifest, and NotebookLM guidance")
    review_en_path = output_dir / "review_EN.md"
    review_en_path.write_text(
        review_template(
            pdf_path.stem,
            review_dir,
            conversion_report.get("status", "UNKNOWN"),
            run_started_dt,
        ),
        encoding="utf-8",
    )

    next_steps_path = review_dir / "NEXT_STEPS.md"
    next_steps_path.write_text(
        next_steps_template(review_dir, ref_summary, lint_summary, source_mode, chunking_mode),
        encoding="utf-8",
    )

    manifest = {
        "version": "codex-1.0",
        "generated_at": run_started_dt.astimezone(timezone.utc).isoformat(),
        "paper": {
            "source_pdf": str(pdf_path),
            "workspace_pdf": str(original_pdf),
            "slug": paper_slug,
        },
        "conversion": {
            "mode": source_mode,
            "status": conversion_report.get("status"),
            "report_path": str(conversion_report_path),
        },
        "chunking": {
            "mode": chunking_mode,
            "chunk_map_path": str(chunk_map_path),
            "total_chunks": chunk_map.get("total_chunks", 0),
        },
        "reference_verification": {
            **ref_summary,
            "report_path": str(reference_report_path),
        },
        "consistency_lint": {
            **lint_summary,
            "report_path": str(lint_report_path),
        },
        "outputs": {
            "review_markdown": str(review_en_path),
            "next_steps": str(next_steps_path),
            "agent_outputs": [str(agent_outputs_dir / f"{name}.md") for name in AGENT_PASSES],
            "notebooklm": {
                "workflow": str(notebooklm_dir / "WORKFLOW.md"),
                "question_log": str(notebooklm_dir / "QUESTION_LOG.md"),
            },
        },
    }

    manifest_path = output_dir / "manifest.json"
    write_json(manifest_path, manifest)

    print("\nReview workspace prepared.")
    print(f"  Directory: {review_dir}")
    print(f"  Source mode: {source_mode}")
    print(f"  Chunking mode: {chunking_mode}")
    print(f"  Conversion: {conversion_report.get('status')}")
    print(
        "  References: "
        f"{ref_summary['verified']} verified, "
        f"{ref_summary['suspicious']} suspicious, "
        f"{ref_summary['unverifiable']} unverifiable"
    )
    print(
        "  Consistency lint: "
        f"{lint_summary['status']} ({lint_summary['finding_count']} findings)"
    )
    print(f"  Next steps: {next_steps_path}")
    return EXIT_OK


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a Codex review workspace from an academic PDF.",
    )
    parser.add_argument(
        "pdf",
        nargs="?",
        help="Path to input PDF (optional: auto-detect a single PDF in current directory)",
    )
    parser.add_argument(
        "--reviews-dir",
        default="reviews",
        help="Root directory for generated review workspaces (default: reviews)",
    )
    parser.add_argument("--name", default=None, help="Optional slug override")
    parser.add_argument(
        "--email",
        default=os.environ.get("REFINE_INK_EMAIL", ""),
        help="Email for CrossRef/OpenAlex polite pool (or set REFINE_INK_EMAIL)",
    )
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
    parser.add_argument(
        "--chunking",
        choices=sorted(CHUNKING_MODES),
        default="chunked",
        help="Chunking strategy for analysis scaffold (default: chunked)",
    )
    parser.add_argument(
        "--pdf-native-only",
        action="store_true",
        help="Skip PDF->Markdown conversion and use direct PDF text extraction.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sys.exit(prepare_review(args))


if __name__ == "__main__":
    main()
