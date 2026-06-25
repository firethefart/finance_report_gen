# Strategy Verifier Human Alignment Export Design

Date: 2026-06-15

## Goal

Export atomic verifier decisions so financial experts can judge one small decision at a time. Experts should not need to read the full verifier report. Each task must contain the same core input available to the verifier, the verifier/LLM output, and a structured feedback form.

## Modules And Alignment Priority

### P0: Chart QA VLM Judge

Atomic unit: one chart candidate judged by the VLM.

Why align: chart quality is central to the project, and crop quality, visual gate, chart-text binding, checklist scoring, and visual professionalism are all partly subjective.

Core input:

- target chart screenshot
- full-page screenshot
- nearby text
- full-page text
- chart metadata: page, bbox, detected title, unit/source/numbers, chart kind hint
- universal and contextual checklist returned by VLM

Verifier output:

- visual gate decision
- VLM checklist scores and evidence
- VLM subscores
- chart-level verifier subscores
- final chart score and issues

Human feedback fields:

- is_target_visual_correct: yes / partial / no
- is_visual_gate_correct: yes / no / unsure
- crop_quality: 0-5
- text_binding_quality: 0-5
- checklist_coverage_quality: 0-5
- score_reasonableness: 0-5
- suggested_score: 0.0-1.0
- main_error_type: no_error / wrong_target / bad_crop / non_visual_not_filtered / missed_context / score_too_high / score_too_low / checklist_gap / evidence_wrong / other
- critical_for_verifier_iteration: yes / no
- expert_rationale: free text

### P0: Claim/Numeric Fact-Level Judge

Atomic unit: one golden key fact checked against candidate evidence and extracted claims.

Why align: this is the most important non-visual factuality path; current scoring can be sensitive to evidence retrieval and unit normalization.

Core input:

- golden fact text, role, expected numbers/dates/entities
- candidate claims extracted from report
- evidence snippets selected for the fact
- numeric audit rows

Verifier output:

- LLM decision: covered / partially_covered / missing / contradicted
- numeric_status
- score
- matched candidate claim ids
- evidence quote
- reason and suggested fix

Human feedback fields:

- coverage_decision_correct: yes / no / partial / unsure
- numeric_status_correct: yes / no / not_applicable / unsure
- evidence_pack_sufficient: yes / partial / no
- unit_normalization_issue: yes / no
- score_reasonableness: 0-5
- suggested_fact_score: 0.0-1.0
- main_error_type: no_error / missing_relevant_evidence / wrong_evidence / numeric_mismatch_missed / numeric_false_alarm / unit_conversion_error / too_strict / too_lenient / other
- critical_for_verifier_iteration: yes / no
- expert_rationale: free text

### P0: Strategy Reasoning Chain Judge

Atomic unit: one extracted reasoning chain judged by the Strategy Reasoning LLM.

Why align: strategy reasoning quality is professional and semantic; it is hard to verify with rules.

Core input:

- expected report type and golden expectation
- one extracted reasoning chain: thesis, supporting facts, mechanism, implication, risk boundary, scenario/counterargument, source context
- programmatic audit row if available

Verifier output:

- chain decision and score
- strengths/gaps
- evidence quote
- suggested fix
- module-level rubric context

Human feedback fields:

- chain_extraction_valid: yes / partial / no
- reasoning_score_reasonable: yes / partial / no / unsure
- thesis_quality: 0-5
- mechanism_quality: 0-5
- evidence_to_conclusion_quality: 0-5
- investment_implication_quality: 0-5
- risk_boundary_quality: 0-5
- suggested_chain_score: 0.0-1.0
- main_error_type: no_error / bad_chain_extraction / missed_reasoning / score_too_high / score_too_low / evidence_quote_wrong / rubric_mismatch / other
- critical_for_verifier_iteration: yes / no
- expert_rationale: free text

### P1: Claim Discipline / Overclaim Judge

Atomic unit: one candidate claim assessed for overclaim risk.

Status: export later if experts have bandwidth. It can be derived from Claim/Numeric LLM outputs.

### P1: Section Coverage / Scenario Risk / Compliance Rules

Atomic unit: one rule issue or module score.

Status: lower expert priority. These modules are mostly deterministic and can be calibrated internally after P0 alignment.

### P2: Scoring Fusion / Gate Thresholds

Atomic unit: one case-level final score and gate outcome.

Status: not suitable as an expert microtask until P0/P1 modules are calibrated. Use later for meta-review.

## Export Artifacts

- `tasks.jsonl`: one JSON object per atomic task.
- `tasks.csv`: flat table for spreadsheet tracking.
- `feedback_schema.json`: JSON Schema for structured expert feedback.
- `feedback_template.csv`: empty spreadsheet-style template.
- `index.html`: local review dashboard with task filters and copied chart assets.
- `assets/`: chart target and full-page screenshots copied from eval results.

## Sampling V1

Default sample budget:

- Chart QA: up to 40 judged chart tasks.
- Claim/Numeric fact checks: up to 35 fact-level tasks.
- Strategy reasoning chains: up to 35 chain-level tasks.

Sampling should cover:

- Chinese and English reports.
- High, medium, and low verifier scores.
- Passing and failing gates.
- At least several low-score or issue-bearing decisions per module.

