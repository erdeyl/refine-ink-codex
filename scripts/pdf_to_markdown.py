#!/usr/bin/env python3
"""
pdf_to_markdown.py - Convert academic PDF papers to clean Markdown.

Uses pymupdf4llm for high-quality PDF-to-Markdown conversion with
automatic multi-column layout handling, and extracts a structured
reference list into a companion JSON file.

Usage:
    python pdf_to_markdown.py input.pdf [--output-dir DIR]

Outputs:
    <filename>_converted.md      - Full Markdown text
    <filename>_references.json   - Structured reference entries
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------
EXIT_OK = 0
EXIT_INPUT_ERROR = 1        # bad arguments / missing file
EXIT_CONVERSION_ERROR = 2   # pymupdf4llm failure
EXIT_IO_ERROR = 3           # cannot write output


# ---------------------------------------------------------------------------
# Reference extraction helpers
# ---------------------------------------------------------------------------

_REF_HEADING_TERMS = {
    "references",
    "bibliography",
    "works cited",
    "literature cited",
    "cited references",
    "reference list",
}

# Headings that would mark the END of the references section
_NEXT_SECTION_RE = re.compile(
    r"^#{1,3}\s+\S|"
    r"^\*{1,2}[A-Z][A-Za-z ]+\*{1,2}\s*$|"
    r"^(Appendix|Supplementary)\b.*$|"
    r"^(Acknowledg(?:e)?ments?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# DOI patterns. Exclude common trailing delimiters captured in prose.
_DOI_RE = re.compile(
    r"(?:doi[:\s]*|https?://(?:dx\.)?doi\.org/)"
    r"(10\.\d{4,}/[^\s\])}>\"',;]+(?:\s+[^\s\])}>\"',;]+)*)",
    re.IGNORECASE,
)

# Year (four digits, commonly 19xx or 20xx)
_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")

# Numbered reference: starts with [1], 1., (1), etc.
_NUMBERED_RE = re.compile(r"^\s*(?:\[(\d+)\]|(\d+)\.\s|\((\d+)\))\s*")

# Author-year style start for non-numbered bibliographies.
_AUTHOR_YEAR_START_RE = re.compile(
    r"^[^\W\d_][^\W\d_'’\-\.]+(?:\s+[^\W\d_][^\W\d_'’\-\.]+){0,3},",
    re.UNICODE,
)

_NUMBERED_HEADING_RE = re.compile(r"^(\d+(?:\.\d+)*)\.\s+(.+?)\s*$")
_PLAIN_HEADING_RE = re.compile(
    r"^(Abstract|Introduction|Literature(?:\s+background)?|Materials\s+and\s+methods|Methods|"
    r"Results|Discussion|Conclusions?|References|Bibliography|Appendix)\s*$",
    re.IGNORECASE,
)
_INSTITUTIONAL_REF_START_RE = re.compile(
    r"^(OECD(?:/European Commission)?|World Health Organization|World Bank|Eurostat|"
    r"European Institute for Gender Equality)\s*\(",
    re.IGNORECASE,
)


def _find_references_section(md_text: str) -> Optional[str]:
    """Return the raw text of the references section, or None."""
    lines = md_text.splitlines(keepends=True)
    if not lines:
        return None

    line_offsets: list[int] = []
    offset = 0
    ref_heading_idx: Optional[int] = None
    for idx, line in enumerate(lines):
        line_offsets.append(offset)
        offset += len(line)
        if _is_reference_heading_line(line):
            ref_heading_idx = idx

    if ref_heading_idx is None:
        return None

    start_offset = line_offsets[ref_heading_idx] + len(lines[ref_heading_idx])
    end_offset = len(md_text)

    for idx in range(ref_heading_idx + 1, len(lines)):
        if _is_next_section_heading(lines[idx]):
            end_offset = line_offsets[idx]
            break

    return md_text[start_offset:end_offset].strip()


def _normalize_heading_line(line: str) -> str:
    stripped = line.strip()
    stripped = re.sub(r"^#{1,6}\s*", "", stripped)
    stripped = stripped.replace("**", "").replace("__", "").replace("*", "").replace("_", "")
    stripped = re.sub(r"^\d+(?:\.\d+)*\s*", "", stripped)
    stripped = re.sub(r"^\(?[ivxlcdm]+\)?\s+", "", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\s+", " ", stripped).strip().lower()
    return stripped


def _is_reference_heading_line(line: str) -> bool:
    return _normalize_heading_line(line) in _REF_HEADING_TERMS


def _is_next_section_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _is_reference_heading_line(stripped):
        return False
    if _is_reference_continuation_heading(stripped):
        return False
    return bool(_NEXT_SECTION_RE.match(stripped))


def _is_reference_continuation_heading(line: str) -> bool:
    if not line.startswith("#"):
        return False
    body = re.sub(r"^#{1,6}\s*", "", line).strip()
    body = body.replace("**", "").replace("__", "").replace("*", "").replace("_", "").strip()
    return bool(
        re.match(
            r"^\d+(?:\.\d+)?\.?\s*(?:\[[^\]]+\]\([^)]+\)|https?://\S+)\s*$",
            body,
            re.IGNORECASE,
        )
        or re.match(r"^\d+(?:\.\d+)?\.?\s*$", body)
    )


def _looks_like_new_reference_line(stripped: str, raw_line: str) -> bool:
    """Heuristic for non-numbered references that start on a new line."""
    if _NUMBERED_RE.match(stripped):
        return True

    # Indented lines are usually continuations of the previous entry.
    if raw_line.startswith((" ", "\t")):
        return False

    # Require an early year marker to avoid splitting on title-case continuation lines.
    has_year_early = bool(
        re.search(r"\((?:19|20)\d{2}[a-z]?\)", stripped[:120])
        or re.search(r"\b(?:19|20)\d{2}[a-z]?\b", stripped[:120])
    )
    if not has_year_early:
        return False

    if _AUTHOR_YEAR_START_RE.match(stripped):
        return True

    # Fallback for styles like "Surname et al. (2020) ..."
    return bool(re.match(r"^[^\W\d_][^!?]{0,100}\((?:19|20)\d{2}[a-z]?\)", stripped, re.UNICODE))


def _split_references(ref_block: str) -> list[str]:
    """Split a references block into individual reference strings."""
    lines = ref_block.splitlines()
    entries: list[str] = []
    current: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            # Ignore blank lines. PDFs often insert empty lines between wrapped
            # lines of the same reference entry.
            continue

        # Split on explicit numbered markers and author-year new-entry cues.
        if current and _looks_like_new_reference_line(stripped, line):
            entries.append(" ".join(current))
            current = []
        elif not current:
            # Start first entry or recover from empty state.
            current = []

        current.append(stripped)

    if current:
        entries.append(" ".join(current))

    # Some converters may concatenate multiple references into one physical line.
    # Split conservatively at sentence boundaries before a likely reference start.
    split_candidates: list[str] = []
    boundary_re = re.compile(
        r"(?<=\.)\s+(?=("
        r"[A-ZÀ-ÖØ-ÝŐŰ][A-Za-zÀ-ÖØ-öø-ÿŐőŰű'’\-]+,\s+[A-ZÀ-ÖØ-ÝŐŰ]"
        r"|OECD(?:/European Commission)?\s*\("
        r"|World Health Organization\s*\("
        r"|World Bank\s*\("
        r"|Eurostat\s*\("
        r"|European Institute for Gender Equality\s*\("
        r"))"
    )
    for entry in entries:
        parts = [p.strip() for p in boundary_re.split(entry) if p.strip()]
        split_candidates.extend(parts)

    # Merge obvious continuation fragments back to the previous reference.
    merged: list[str] = []
    for entry in split_candidates:
        starts_new = bool(_AUTHOR_YEAR_START_RE.match(entry) or _INSTITUTIONAL_REF_START_RE.match(entry))
        if not merged:
            merged.append(entry)
            continue
        if starts_new:
            merged.append(entry)
            continue
        merged[-1] = f"{merged[-1]} {entry}"

    return [e for e in merged if len(e) > 15]  # discard very short fragments


def _extract_authors(text: str) -> str:
    """Heuristic extraction of author names from the beginning of a reference."""
    # Remove leading number markers
    cleaned = _NUMBERED_RE.sub("", text).strip()

    # Common pattern: authors come before the year or before a title in quotes/italics
    # Try splitting on the first year occurrence
    year_match = _YEAR_RE.search(cleaned)
    if year_match:
        before_year = cleaned[: year_match.start()].strip().rstrip("(.,;")
        if 5 < len(before_year) < 500:
            return before_year

    # Fallback: take text up to the first period
    dot_pos = cleaned.find(".")
    if 5 < dot_pos < 300:
        return cleaned[:dot_pos].strip()

    return ""


def _extract_title(text: str) -> str:
    """Heuristic extraction of the title from a reference entry."""
    cleaned = _NUMBERED_RE.sub("", text).strip()

    # Try to find a quoted title
    quoted = re.search(r'["\u201c](.+?)["\u201d]', cleaned)
    if quoted and len(quoted.group(1)) > 10:
        return quoted.group(1).strip()

    # Try to find an italic title (*title* or _title_)
    italic = re.search(r"[*_](.+?)[*_]", cleaned)
    if italic and len(italic.group(1)) > 10:
        return italic.group(1).strip()

    # Fallback: text between first period and second period after the year
    year_match = _YEAR_RE.search(cleaned)
    if year_match:
        after_year = cleaned[year_match.end():].strip().lstrip(".)],;: ")
        dot_pos = after_year.find(".")
        if dot_pos > 10:
            return after_year[:dot_pos].strip()

    return ""


def _extract_journal(text: str) -> str:
    """Heuristic extraction of journal name."""
    # Look for italic text that is NOT the title (often the journal)
    italics = re.findall(r"[*_]([^*_]+)[*_]", text)
    if len(italics) >= 2:
        # Second italic block is often the journal
        return italics[1].strip()
    if len(italics) == 1:
        candidate = italics[0].strip()
        # If it looks like a journal (contains uppercase, not too long)
        if len(candidate) < 120:
            return candidate

    return ""


def _parse_reference(raw_text: str) -> dict:
    """Parse a single reference string into a structured dict."""
    cleaned_text = _repair_split_doi(raw_text)
    doi_match = _DOI_RE.search(cleaned_text)
    year_match = _YEAR_RE.search(cleaned_text)
    cleaned_doi = ""
    if doi_match:
        cleaned_doi = (
            doi_match.group(1)
            .replace(" ", "")
            .strip()
            .strip("<>{}")
            .rstrip(".,;:)]}'\"")
        )

    return {
        "title": _extract_title(cleaned_text),
        "authors": _extract_authors(cleaned_text),
        "year": year_match.group(1) if year_match else "",
        "doi": cleaned_doi,
        "journal": _extract_journal(cleaned_text),
        "raw_text": cleaned_text.strip(),
    }


def extract_references(md_text: str) -> list[dict]:
    """Extract structured references from the Markdown text."""
    ref_section = _find_references_section(md_text)
    if not ref_section:
        return []

    entries = _split_references(ref_section)
    return [_parse_reference(entry) for entry in entries]


def _repair_split_doi(text: str) -> str:
    cleaned = re.sub(
        r"(https?://(?:dx\.)?doi\.org/)\s+",
        r"\1",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\bdoi:\s+", "doi:", cleaned, flags=re.IGNORECASE)

    def _compact(match: re.Match[str]) -> str:
        return match.group(0).replace(" ", "")

    cleaned = re.sub(
        r"10\.\d{4,}/[A-Za-z0-9._;()/:\-]+(?:\s+[A-Za-z0-9._;()/:\-]+)+",
        _compact,
        cleaned,
    )
    cleaned = re.sub(
        r"https?://(?:dx\.)?doi\.org/[A-Za-z0-9._;()/:\-]+(?:\s+[A-Za-z0-9._;()/:\-]+)+",
        _compact,
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned


def _extract_references_from_pdf_text(pdf_path: Path) -> list[dict]:
    try:
        import pymupdf  # type: ignore
    except ImportError:
        return []

    try:
        doc = pymupdf.open(str(pdf_path))
        pdf_text = "\n".join(page.get_text("text") for page in doc)
        doc.close()
    except Exception:
        return []

    ref_section = _find_references_section(pdf_text)
    if not ref_section:
        return []

    entries = _split_references(ref_section)
    parsed = [_parse_reference(entry) for entry in entries]
    return [item for item in parsed if item.get("raw_text")]


def extract_references_from_pdf(pdf_path: Path) -> list[dict]:
    """Public helper: extract structured references directly from PDF text."""
    return _extract_references_from_pdf_text(pdf_path)


# ---------------------------------------------------------------------------
# Conversion statistics
# ---------------------------------------------------------------------------

def _compute_stats(md_text: str, page_count: int) -> dict:
    """Compute conversion statistics from the Markdown output."""
    words = len(md_text.split())
    sections = len(re.findall(r"^#{1,6}\s+", md_text, re.MULTILINE))
    # Count markdown tables (lines starting with |)
    table_rows = re.findall(r"^\|.+\|$", md_text, re.MULTILINE)
    # A table is a contiguous block of | rows.  Count separator rows as proxy.
    table_count = len(re.findall(r"^\|[\s\-:|]+\|$", md_text, re.MULTILINE))

    return {
        "pages": page_count,
        "words": words,
        "sections": sections,
        "tables": table_count,
    }


def _should_promote_heading(lines: list[str], idx: int, stripped: str) -> bool:
    if len(stripped) > 120:
        return False
    prev_blank = idx == 0 or not lines[idx - 1].strip()
    next_blank = idx == len(lines) - 1 or not lines[idx + 1].strip()
    return prev_blank or next_blank


def _heading_level_from_number(number: str) -> int:
    # 1. -> ##, 2.1. -> ###, 3.1.2. -> ####
    depth = number.count(".") + 1
    return min(4, depth + 1)


def _recover_markdown_headings(md_text: str) -> str:
    """Promote plain numbered section titles to Markdown headings."""
    lines = md_text.splitlines()
    recovered: list[str] = []

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            recovered.append("")
            continue

        # Keep headings emitted by converter.
        if re.match(r"^#{1,6}\s+", stripped):
            recovered.append(stripped)
            continue

        if _should_promote_heading(lines, idx, stripped):
            numbered = _NUMBERED_HEADING_RE.match(stripped)
            if numbered:
                number = numbered.group(1)
                title = numbered.group(2)
                if re.search(r"[A-Za-zÀ-ÖØ-öø-ÿŐőŰű]", title):
                    level = _heading_level_from_number(number)
                    recovered.append(f"{'#' * level} {number}. {title}")
                    continue

            if _PLAIN_HEADING_RE.match(stripped):
                recovered.append(f"## {stripped}")
                continue

        recovered.append(line.rstrip())

    return "\n".join(recovered)


def _print_stats(stats: dict) -> None:
    print("\n--- Conversion Statistics ---")
    print(f"  Pages:    {stats['pages']}")
    print(f"  Words:    {stats['words']}")
    print(f"  Sections: {stats['sections']}")
    print(f"  Tables:   {stats['tables']}")
    print("-----------------------------\n")


# ---------------------------------------------------------------------------
# Main conversion logic
# ---------------------------------------------------------------------------

def convert_pdf(pdf_path: Path, output_dir: Optional[Path] = None) -> int:
    """Convert a PDF to Markdown + references JSON. Returns an exit code."""
    # ------------------------------------------------------------------
    # 1. Validate input
    # ------------------------------------------------------------------
    if not pdf_path.is_file():
        print(f"Error: file not found: {pdf_path}", file=sys.stderr)
        return EXIT_INPUT_ERROR

    if pdf_path.suffix.lower() != ".pdf":
        print(f"Error: not a PDF file: {pdf_path}", file=sys.stderr)
        return EXIT_INPUT_ERROR

    # ------------------------------------------------------------------
    # 2. Determine output paths
    # ------------------------------------------------------------------
    if output_dir is None:
        output_dir = pdf_path.parent
    output_dir = Path(output_dir)

    if not output_dir.is_dir():
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(f"Error: cannot create output directory: {exc}", file=sys.stderr)
            return EXIT_IO_ERROR

    stem = pdf_path.stem
    md_path = output_dir / f"{stem}_converted.md"
    refs_path = output_dir / f"{stem}_references.json"

    # ------------------------------------------------------------------
    # 3. Convert PDF -> Markdown via pymupdf4llm
    # ------------------------------------------------------------------
    try:
        import pymupdf4llm  # type: ignore
        import pymupdf       # type: ignore  (fitz)
    except ImportError as exc:
        print(
            f"Error: required package not installed: {exc}\n"
            "Install with:  pip install pymupdf4llm",
            file=sys.stderr,
        )
        return EXIT_CONVERSION_ERROR

    print(f"Converting: {pdf_path}")

    try:
        md_text: str = pymupdf4llm.to_markdown(
            str(pdf_path),
            ignore_graphics=False,
            page_separators=True,
            show_progress=False,
        )
    except Exception as exc:
        print(f"Error during PDF conversion: {exc}", file=sys.stderr)
        return EXIT_CONVERSION_ERROR

    # Get page count from PyMuPDF directly
    try:
        doc = pymupdf.open(str(pdf_path))
        page_count = doc.page_count
        doc.close()
    except Exception:
        page_count = 0

    # ------------------------------------------------------------------
    # 4. Post-process: light clean-up
    # ------------------------------------------------------------------
    md_text = re.sub(r"^\s*---\s*end of page=\d+\s*---\s*$", "", md_text, flags=re.MULTILINE)
    md_text = _recover_markdown_headings(md_text)
    # Collapse runs of 3+ blank lines into 2
    md_text = re.sub(r"\n{4,}", "\n\n\n", md_text)
    # Strip trailing whitespace on each line
    md_text = "\n".join(line.rstrip() for line in md_text.splitlines()) + "\n"

    # ------------------------------------------------------------------
    # 5. Write Markdown output
    # ------------------------------------------------------------------
    try:
        md_path.write_text(md_text, encoding="utf-8")
        print(f"Markdown saved: {md_path}")
    except OSError as exc:
        print(f"Error writing Markdown: {exc}", file=sys.stderr)
        return EXIT_IO_ERROR

    # ------------------------------------------------------------------
    # 6. Extract and write references
    # ------------------------------------------------------------------
    references = extract_references(md_text)
    if len(references) < 3:
        fallback_refs = _extract_references_from_pdf_text(pdf_path)
        if len(fallback_refs) > len(references):
            references = fallback_refs
            print(
                f"Reference fallback used (PDF-native parsing): {len(references)} entries"
            )
    try:
        refs_path.write_text(
            json.dumps(references, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"References saved: {refs_path}  ({len(references)} entries)")
    except OSError as exc:
        print(f"Error writing references JSON: {exc}", file=sys.stderr)
        return EXIT_IO_ERROR

    # ------------------------------------------------------------------
    # 7. Print statistics
    # ------------------------------------------------------------------
    stats = _compute_stats(md_text, page_count)
    _print_stats(stats)

    return EXIT_OK


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert an academic PDF to clean Markdown with reference extraction.",
    )
    parser.add_argument(
        "pdf",
        type=Path,
        help="Path to the input PDF file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for output files (default: same directory as the PDF).",
    )

    args = parser.parse_args()
    return convert_pdf(args.pdf, args.output_dir)


if __name__ == "__main__":
    sys.exit(main())
