#!/usr/bin/env python3
"""Shared helpers for detecting reference-section headings."""

from __future__ import annotations

import re
import unicodedata

REF_HEADING_TERMS = {
    "references",
    "bibliography",
    "works cited",
    "literature cited",
    "cited references",
    "reference list",
    "irodalom",
    "hivatkozasok",
    "hivatkozas",
}


def normalize_heading_label(text: str) -> str:
    """Normalize a heading label for cross-module comparisons."""
    cleaned = text.strip()
    cleaned = re.sub(r"^#{1,6}\s*", "", cleaned)
    cleaned = cleaned.replace("**", "").replace("__", "").replace("*", "").replace("_", "")
    cleaned = re.sub(r"^\d+(?:\.\d+)*\.?\s*", "", cleaned)
    cleaned = re.sub(r"^\(?[ivxlcdm]+\)?[.)]?\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    folded = unicodedata.normalize("NFD", cleaned)
    return "".join(ch for ch in folded if unicodedata.category(ch) != "Mn")


def is_reference_heading_line(text: str) -> bool:
    return normalize_heading_label(text) in REF_HEADING_TERMS


def find_last_reference_heading(lines: list[str]) -> int | None:
    last_idx: int | None = None
    for idx, line in enumerate(lines):
        if is_reference_heading_line(line):
            last_idx = idx
    return last_idx
