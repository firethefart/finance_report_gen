# Candidate-Only Verifier Session Handoff — 2026-06-19 — Rules Run r8

## Current baseline

```text
evals/strategy_report/results/candidate_only_rules_r8/
```

- requested 26;
- completed 26;
- report-level failures 0;
- gate passed 19/26.

`V2` continues to mean the no-reference candidate-only verifier variant. `r8`
is an engineering run label, not “Verifier V8”.

## Changes

### Full text versus analysis text

HTML parsing now retains two text channels:

- `full_text`: complete rendered page text, used by compliance and delivery;
- `analysis_text`: research body only, used by structure, sources, numeric
  discipline, strategy reasoning and scenario/risk.

The parser records:

- boundary mode;
- full and analytical text lengths;
- trimmed character count;
- matched boundary marker.

### HTML content boundaries

General boundary signals include:

- `Discover More`;
- disclosures/risk-consideration sections;
- repeated related-content category cards.

Only two real HTML reports were trimmed in the full run:

- Morgan Stanley Equity Rally: 17,509 → 5,155 characters at `Discover More`;
- Morgan Stanley Digital Assets: 6,374 → 6,190 characters at related cards.

All GSAM and State Street reports retained their full text.

### Section recovery

- Numbered prose sections can become synthetic headings when the DOM exposes
  fewer than five real headings.
- Synthetic heading recovery is disabled for pages already containing five or
  more DOM headings.
- Candidates beginning with `Source:` are rejected.
- Headings outside the retained analytical text are removed.
- Structure vocabulary now recognizes generic evidence and positioning terms
  such as `analysis`, `forecast`, `estimate`, `positioning` and `preference`.

### Strategy evidence

Generic portfolio expressions such as `tilting portfolios`, `target`,
`opportunity set` and `for investors` are recognized as explicit investment
implications or views.

## Key regression results

- Morgan Stanley Equity Rally:
  - r7: 73.80;
  - r8: 74.71;
  - analysis body 5,155 characters;
  - strategy reasoning 0.798 using body-only evidence;
  - still rejected, without changing the gate.
- Morgan Stanley Digital Assets:
  - r7: 65.32;
  - r8: 67.28;
  - structure 0.500 → 0.653;
  - still rejected due weak source traceability and limited report depth.
- GSAM Fed:
  - false synthetic `Source:` heading was removed;
  - final score 83.59, passed.
- Gate pass/reject set is identical to r7.
- Generated optimized remains above generated baseline.

## Layered results

- HTML: 78.57, gate 6/12;
- PDF: 85.99, gate 13/14;
- English: 78.85, gate 7/14;
- Chinese: 86.90, gate 12/12.

Artifacts:

- `evals/strategy_report/results/candidate_only_rules_r8/summary.json`
- `evals/strategy_report/results/candidate_only_rules_r8/layered_summary.json`
- `evals/strategy_report/results/candidate_only_rules_r8/layered_summary.md`

## Failures and warnings

- The first boundary implementation searched only after 45% of the page.
  Morgan Stanley Equity Rally disclosures begin near 29%, so the parser
  incorrectly trimmed only the final 17 characters at `View Disclosures`.
- The search threshold was corrected to 20%; the rerun trimmed 12,354
  non-analytical characters at `Discover More`.
- The first synthetic-heading implementation interpreted a GSAM `Source:`
  line as section 1 and increased its score. Synthetic headings are now used
  only when DOM headings are sparse, and `Source:` candidates are rejected.
- GSAM Active ETF continues to emit the known non-fatal MuPDF structure-tree
  warning.
- Final Python compilation passed.

## Next work

1. Audit J.P. Morgan Energy sample scope and text compaction.
2. Decide whether it is a strategy-quality sample or only a thematic parser
   robustness case.
3. Inspect the remaining language/format gap without reducing thresholds.
4. After deterministic convergence, begin layered LLM/VLM runs.
