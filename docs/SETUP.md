# Setup Guide

Install and configure `refine-ink-codex` for local use in Codex.

## Prerequisites

| Requirement | Version | Check |
|---|---|---|
| Python | 3.10+ | `python3 --version` |
| pip | recent | `pip --version` |
| git | recent | `git --version` |

Optional:

| Requirement | Purpose |
|---|---|
| Semantic Scholar API key | Higher throughput for reference verification |

## 1. Clone

```bash
git clone https://github.com/erdeyl/refine-ink-codex.git
cd refine-ink-codex
```

## 2. Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r scripts/requirements.txt
```

Installed packages:

- `pymupdf4llm` for PDF -> Markdown conversion
- `pymupdf` for direct PDF text/table extraction in verification
- `httpx` for async API requests
- `markdown` and `jinja2` for HTML rendering
- `bleach` for report HTML sanitization

## 3. (Optional) Set Semantic Scholar API Key

```bash
export S2_API_KEY="your_api_key_here"
```

You can also pass it per run:

```bash
python scripts/codex_prepare_review.py path/to/paper.pdf --s2-api-key your_api_key_here
```

## 4. Verify Installation

```bash
python scripts/codex_prepare_review.py --help
python scripts/pdf_to_markdown.py --help
python scripts/verify_conversion.py --help
python scripts/verify_references.py --help
python scripts/md_to_html.py --help
```

## 5. First Run

```bash
python scripts/codex_prepare_review.py [path/to/paper.pdf] --email you@example.com
```

If `path/to/paper.pdf` is omitted, the script auto-detects a single `.pdf` in the current directory.

This creates `reviews/<paper>_<YYYY-MM-DD>/` with deterministic outputs and analysis scaffolds.

## Troubleshooting

### Conversion fails

- Check the PDF is text-based and not encrypted
- Update parser stack:
  - `pip install --upgrade pymupdf4llm pymupdf`

### Reference verification is slow

- Use `S2_API_KEY` for higher Semantic Scholar limits
- For quick setup tests, use `--skip-references`

### Missing `fitz` / PyMuPDF

- Install directly:
  - `pip install pymupdf`
