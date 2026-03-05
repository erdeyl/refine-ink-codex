# refine-ink-codex -- Scientific Paper Review Workflow for Codex

> Codex-native adaptation of [Refine.ink](https://refine.ink)-style academic paper review.

![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)
![Status: Alpha](https://img.shields.io/badge/Status-Alpha-orange.svg)

## What This Repo Provides

- Deterministic preprocessing of academic PDFs (PDF -> Markdown + conversion checks)
- Rule-based manuscript consistency lint to flag common internal-logic issues early
- Reference verification against CrossRef, OpenAlex, and Semantic Scholar
- Codex-ready review workspace scaffolding (`chunks`, `agent_outputs`, `output`)
- Structured report and manifest templates for reproducible audits
- Styled HTML rendering of final Markdown reports

## Quick Start

```bash
git clone https://github.com/erdeyl/refine-ink-codex.git
cd refine-ink-codex
python3 -m venv .venv
source .venv/bin/activate
pip install -r scripts/requirements.txt

python scripts/codex_prepare_review.py path/to/paper.pdf --email you@example.com
```

After preparation completes, continue review passes in the generated workspace and finalize `output/review_EN.md`.

If no path is provided, the script auto-detects a single `.pdf` in the current directory.

## Codex App Workflow

1. Open the repository in the Codex app.
2. Use the plus button to upload a PDF.
3. Type `/review`.
4. The agent resolves the uploaded PDF and runs:
   - `python scripts/codex_prepare_review.py <resolved_pdf_path>`

## Review Workflow (Codex)

1. Run deterministic preparation:
   - `python scripts/codex_prepare_review.py [path/to/paper.pdf]`
2. Open `reviews/<paper>_<date>/NEXT_STEPS.md`
3. Fill analysis outputs under `agent_outputs/`:
   - `math-logic.md`, `notation.md`, `exposition.md`, `empirical.md`, `cross-section.md`, `econometrics.md`, `literature.md`, `references.md`, `language.md`
4. Synthesize the final report in `output/review_EN.md` (and `review_HU.md` when needed)
5. Render HTML:
   - `python scripts/md_to_html.py reviews/<paper>_<date>/output/review_EN.md`

## Deterministic Outputs

Each prepared review contains:

- `input/original.pdf`
- `input/original_converted.md`
- `input/original_references.json`
- `verification/original_verification.json`
- `verification/consistency_lint_report.json`
- `verification/reference_report.json`
- `chunks/chunk_map.json` (`total_chunks`, `chunks[]`, `dimension_assignments`)
- `agent_outputs/*.md` (scaffolded)
- `output/review_EN.md`
- `output/manifest.json`
- `NEXT_STEPS.md`

## Repository Layout

```text
refine-ink-codex/
  AGENTS.md
  scripts/
    codex_prepare_review.py
    pdf_to_markdown.py
    verify_conversion.py
    verify_references.py
    md_to_html.py
    review_template.html
  docs/
    SETUP.md
    USAGE.md
    ARCHITECTURE.md
    AUDIT.md
    CHUNKING.md
    AGENTS.md
  legacy/
    claude/                 # Original Claude-specific assets retained for reference
```

## Documentation

- [docs/SETUP.md](docs/SETUP.md)
- [docs/USAGE.md](docs/USAGE.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/AUDIT.md](docs/AUDIT.md)
- [docs/CHUNKING.md](docs/CHUNKING.md)
- [docs/AGENTS.md](docs/AGENTS.md)

## Legacy Claude Assets

Original orchestration assets from the upstream Claude workflow are preserved under `legacy/claude/`.

## License

MIT License. See [LICENSE](LICENSE).
