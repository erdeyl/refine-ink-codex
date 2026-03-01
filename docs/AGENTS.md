# Analysis Passes

The Codex workflow uses nine analysis dimensions. These are not hard-coded model agents; they are structured review passes you execute in `agent_outputs/`.

## Overview

| Pass | Focus | Primary Output |
|---|---|---|
| math-logic | Equations, derivations, proofs | `agent_outputs/math-logic.md` |
| notation | Symbols, variables, acronym consistency | `agent_outputs/notation.md` |
| exposition | Argument flow, clarity, section coherence | `agent_outputs/exposition.md` |
| empirical | Tables/figures vs text consistency | `agent_outputs/empirical.md` |
| cross-section | Contradictions across sections | `agent_outputs/cross-section.md` |
| econometrics | Identification and statistical design quality | `agent_outputs/econometrics.md` |
| literature | Coverage of relevant prior work | `agent_outputs/literature.md` |
| references | Bibliography quality + suspicious entries | `agent_outputs/references.md` |
| language | Academic writing quality (EN/HU) | `agent_outputs/language.md` |

## Required Finding Format

Each finding should include:

- Assertion-style title (a conclusion, not a label)
- Severity: Critical, Major, Minor, Suggestion
- Confidence: 0-100
- Location in source markdown (section/line context)
- Verbatim evidence snippet
- Concrete correction recommendation

## Pass Guidance

### math-logic

Check algebraic steps, symbol binding, proof completeness, and logical validity.

### notation

Track definitions and reuse of symbols, subscripts, and acronyms across the paper.

### exposition

Assess whether abstract, introduction, methods, results, and conclusion align logically.

### empirical

Cross-check every reported value in text against tables/figures. Flag sign, magnitude, and significance mismatches.

### cross-section

Compare distant sections directly (intro vs results, methods vs results, abstract vs conclusion).

### econometrics

Evaluate identification assumptions, standard error treatment, endogeneity handling, and robustness design.

### literature

Identify missing seminal work or mispositioned novelty claims.

### references

Interpret `verification/reference_report.json` and flag improbable or inconsistent entries.

### language

Detect readability issues, ambiguous phrasing, and register inconsistencies. For Hungarian papers, enforce proper academic HU usage.

## Quality Rules

- Every claim must be grounded in text from `input/original_converted.md`
- Distinguish observed fact from inference
- Keep uncertain claims in a low-confidence appendix
- Do not edit input files under `input/`
