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
| NotebookLM MCP in Codex | Grounded text-analysis sidecar during review and synthesis |

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
- `nh3` (preferred) and `bleach` (fallback) for report HTML sanitization

## 3. (Optional) Set Semantic Scholar API Key

```bash
export S2_API_KEY="your_api_key_here"
```

The workflow reads this from the environment only to avoid leaking secrets via shell history or process lists.

## 4. (Optional) Configure NotebookLM MCP In Codex

This repository does not vendor a NotebookLM client. Configure NotebookLM in your Codex environment separately if it is available there.

Once configured, each prepared review workspace includes:

- `notebooklm/WORKFLOW.md`
- `notebooklm/QUESTION_LOG.md`

Use NotebookLM after deterministic preparation, during each analysis pass, and again before final synthesis or joint workflow comparison.

## 5. Verify Installation

```bash
python scripts/codex_prepare_review.py --help
python scripts/pdf_to_markdown.py --help
python scripts/verify_conversion.py --help
python scripts/verify_references.py --help
python scripts/md_to_html.py --help
```

## 6. First Run

```bash
python scripts/codex_prepare_review.py [path/to/paper.pdf] --email you@example.com
```

If `path/to/paper.pdf` is omitted, the script auto-detects a single `.pdf` in the current directory.

This creates `reviews/<paper>_<YYYY-MM-DD>/` with deterministic outputs and analysis scaffolds.

In the Codex app workflow, you can upload a PDF and type `/review`; the agent should resolve the uploaded file and run the same command.

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
