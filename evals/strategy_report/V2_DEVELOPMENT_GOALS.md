# Verifier V2 Development Goals

Last updated: 2026-06-19

Terminology: **V2 identifies the candidate-only, no-reference verifier
variant. It is not an iteration number.** Engineering runs are named `rN`;
older directories containing `_vN` are retained as legacy run labels.

## Long-Term Objective

Build a high-quality, candidate-only verifier for financial strategy research
reports. The verifier must work on both HTML and PDF without depending on a
golden reference report, while preserving generalizable parsing, evidence,
reasoning, visual, risk, and compliance methods rather than institution- or
sample-specific hard coding.

Project sequence:

1. Optimize Verifier V2 close to its practical engineering ceiling.
2. Build the automated strategy-report generation pipeline.
3. Start verifier-driven skill iteration.
4. Run expensive expert alignment after inexpensive engineering improvements
   have substantially converged.

## Current Development Stage

**Stage: Verifier V2 optimization**

Current priorities:

- Build a representative, high-quality HTML/PDF test set.
- Find and fix systematic verifier errors across language, format, subtype, and
  report archetype.
- Improve HTML runtime fidelity, chart selection, source traceability,
  candidate-only factual discipline, and archetype-aware strategy reasoning.
- Keep expert alignment as a later calibration stage, not the immediate next
  step.

## Test-Set Target

The V2 core test set should contain 20–30 high-quality strategy reports.

Required properties:

- HTML is a primary format, not a token minority.
- At least 10 high-quality HTML reports beyond the two local generated examples.
- Chinese and English coverage.
- Annual/midyear/quarterly outlook, asset allocation, macro/rates/credit,
  equity/market structure, thematic/industry, weekly/brief, M&A/capital markets,
  and implementation-oriented reports.
- Deep-dive, standard, weekly/brief, chartbook, and implementation archetypes.
- Core HTML must render locally without missing critical resources.
- Synthetic fixtures remain separate from report-quality evaluation samples.
- No sample is admitted merely to satisfy a count.

## Quality Policy

- Technical difficulty must be debugged or discussed; it is not grounds for
  silently weakening admission criteria.
- Broken HTML must not be reclassified as a text-only core sample.
- Missing charts must not be replaced by decorative placeholders.
- PDF-to-HTML conversion must not hallucinate or rewrite report content.
- Source provenance, hashes, localization method, and known limitations must be
  recorded.
- Any quarantined sample remains outside the core set until the underlying
  problem is fixed.

## Iteration Log

### Iteration 1 — Initial 24-report core set

Status: **Completed, but superseded for format balance**

Summary:

- Built a 24-report set with 12 English and 12 Chinese reports.
- Included 22 PDFs and 2 self-contained local HTML reports.
- Added repeatable hard-audit and batch-run tools.
- All 24 files passed integrity and V2 compatibility checks.
- The set exposed systematic scoring problems, including unexpectedly low
  scores for several strong English deep-dive reports.

Shortcoming discovered:

- HTML coverage was materially insufficient.
- The two HTML reports were both local versions of the same topic and were not
  strong enough to represent the primary future deployment format.

Decision:

- Rebalance the set toward high-quality, locally renderable HTML.
- Add at least 10 HTML reports and replace PDFs where necessary to keep the core
  set within 20–30 reports.

### Iteration 2 — High-quality HTML expansion

Status: **Completed**

Completion checklist:

- [x] HTML candidate audit completed.
- [x] Localization workflow implemented and audited.
- [x] Ten real-institution HTML reports pass strict admission.
- [x] Core manifest rebalanced to 26 reports.
- [x] Full hard audit passes 26/26.
- [x] Unified rules run completes 26/26 without report-level exception.
- [x] Iteration summary and handoff recorded.

Important qualification:

The first unified run exposed a Windows long-path bug in HTML Runtime Adapter
browser navigation. Eleven HTML samples opened as `ERR_FILE_NOT_FOUND`, so their
scores are invalid even though the batch technically completed.

### Iteration 3 — Repair unified HTML baseline

Status: **Completed**

- [x] Make the Runtime Adapter open a short temporary browser path.
- [x] Verify a previously failing HTML restores its full text and visuals.
- [x] Re-run the 26-report rules baseline into a new output directory.
- [x] Produce format/language/archetype/subtype summaries.
- [x] Diagnose real verifier bias only after the adapter baseline is valid.

Results:

- The GSAM Backdrop sample restored 50,062 characters and 10 visual objects.
- Its full Verifier result restored to 91.65, Gold, gate passed.
- `v2_core_26_unified_rules_v2` completed 26/26 with zero report-level failures.
- HTML averaged 75.41 versus PDF 84.07.
- English averaged 75.52 versus Chinese 85.39.
- The largest actionable gaps are strategy reasoning, HTML section/context
  binding, brief/chartbook archetype handling, and HTML visual-object scoring.

### Iteration 4 — Repair deterministic reasoning and HTML visual false positives

Status: **Completed**

- [x] Restore Chinese/English sentence splitting and corrupted rule terms.
- [x] Prevent incidental source names such as `Carbon Brief` from changing the
  report archetype.
- [x] Infer chartbooks from primary headings or visual density.
- [x] Recover sentence-level thesis, mechanism, implication, and risk evidence.
- [x] Exclude high-confidence decorative HTML images from rule-only chart score.
- [x] Re-run all 26 reports and produce the legacy r3 layered summary.

Results:

- 26/26 completed with zero report-level failures.
- State Street Alternatives and BlackRock chartbook changed from false rejects
  to passes for evidence-backed reasons.
- Morgan Stanley Digital Assets and J.P. Morgan Energy remain rejected, so the
  change did not indiscriminately pass every strong-looking report.
- HTML averaged 80.18 and PDF 87.82.
- English averaged 80.62 and Chinese 88.59.
- Nine reports now saturate strategy reasoning at 1.0; this is the next
  deterministic calibration concern.

### Engineering iteration 5 — Restore strategy-reasoning ranking resolution

Status: **Completed**

- [x] Replace early hard caps with archetype-aware soft saturation.
- [x] Remove duplicate and disclaimer evidence before reasoning scoring.
- [x] Remove unreliable chart-extractor density from archetype inference.
- [x] Pass authoritative manifest titles into the evaluator.
- [x] Detect additional explicit thesis/view formulations.
- [x] Preserve failed legacy r4 regression evidence and produce corrected
  legacy r5.

Results:

- Legacy run r5 (`...unified_rules_v5`) completed 26/26 with zero report-level
  failures.
- Exact strategy reasoning 1.0 scores fell from 9 to 0.
- Two reports remain at or above 0.99, instead of nine.
- State Street Alternatives briefly regressed in v4, then recovered to 77.30
  in v5 through evidence detection rather than a lower gate.
- HTML averaged 80.65 and PDF 87.25.
- English averaged 81.01 and Chinese 87.94.
- Gate pass count is 21/26.

### Engineering iteration 6 — Correct source and numeric evidence semantics

Status: **Completed**

- [x] Establish `candidate_only_rules_rN` naming.
- [x] Fix four-digit and currency/duration numeric extraction.
- [x] Filter document IDs, year-only headings and publication metadata.
- [x] Stop counting author, footer and home-page links as sources.
- [x] Separate publisher provenance from external source traceability.
- [x] Run intermediate r6 and final r7 without overwriting failure evidence.

Results:

- r7 completed 26/26 with zero report-level failures.
- Gate pass count is 19/26.
- GSAM Backdrop remains 92.87 and passes.
- BlackRock chartbook remains 82.99 and passes.
- Generated optimized remains 11.55 points above generated baseline.
- State Street pages are now penalized for missing traceable data sources rather
  than rewarded for author/navigation links.
- HTML averages 78.09 versus PDF 85.74.
- English averages 78.19 versus Chinese 86.90.

### Engineering iteration 7 — Separate HTML research body from disclosures

Status: **Completed**

- [x] Preserve full rendered text for compliance.
- [x] Use analysis-only text for research-quality dimensions.
- [x] Detect related cards and disclosure boundaries.
- [x] Recover numbered prose sections when DOM headings are sparse.
- [x] Reject `Source:` lines as synthetic headings.
- [x] Re-run all 26 reports as candidate-only rules r8.

Results:

- r8 completed 26/26 with zero report-level failures.
- Gate pass count remains 19/26.
- Morgan Stanley Equity Rally now scores body-only reasoning and remains a
  74.71 borderline reject.
- Morgan Stanley Digital Assets structure improves from 0.500 to 0.653 but
  remains rejected at 67.28.
- Only the two Morgan Stanley pages triggered HTML body trimming.
- HTML averages 78.57 and PDF 85.99.
- English averages 78.85 and Chinese 86.90.

## Next Development Plan

This section is updated at the end of every iteration.

1. Determine whether J.P. Morgan Energy is a strategy report or a thematic
   research robustness case, and audit its head/tail text compaction.
2. Inspect the remaining language/format gap without reducing thresholds.
3. Re-run all 26 reports after every material rules change.
4. Run layered LLM/VLM modules only after deterministic engineering errors have
   converged; do not start expert alignment yet.

See `SESSION_HANDOFF_20260619_CANDIDATE_ONLY_R8.md` for exact evidence and commands.
