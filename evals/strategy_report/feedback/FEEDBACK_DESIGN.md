# Strategy Verifier Feedback Design

Status: draft v0.1  
Date: 2026-06-27  
Scope: reference-based verifier and candidate-only/no-reference verifier

## 1. Why this exists

The verifier is no longer only a scoring tool. Its production value depends on whether
the evaluation result can be turned into useful, readable feedback for skill iteration.

The feedback layer should answer three questions:

1. What is the current generated-report quality?
2. Where does the verifier agree or disagree with human judgement?
3. What should the report-generation skill or model setup change next?

This feedback must be useful for two reader groups:

- Human readers:
  - financial experts who want to audit quality and verifier-human alignment;
  - non-expert operators who need a clear status overview and triage path.
- Agent readers:
  - agents that inspect verifier output, locate related skill/code/prompt entries, and
    draft concrete revision plans.

Therefore the primary feedback artifact should be readable and structured, not a large
raw JSON dump. JSON can exist as a machine-supporting artifact, but the canonical user
experience should be a navigable Markdown/HTML report with stable sections, evidence
links, and compact structured blocks.

## 2. Design principles

1. Human-readable first, machine-stable underneath.
   - The main artifact should be concise Markdown or HTML.
   - A compact structured sidecar may exist for automation, but should not be the only
     useful output.

2. Feedback is not just a list of verifier issues.
   - It should translate scores and judge rationales into skill-iteration actions.
   - It should distinguish symptoms, probable causes, and concrete fixes.

3. V1 and candidate-only/no-reference share the feedback framework.
   - V1 has a reference/query/source contract and can give stronger feedback on factual
     coverage, grounding, and model selection.
   - Candidate-only/no-reference has weaker factual certainty but can still provide rich
     feedback on content quality, strategy reasoning, visual QA, structure, writing, and
     HTML delivery.

4. Feedback should preserve evidence.
   - Each important recommendation should link back to verifier evidence: module result,
     chart id, claim id, section id, text span, screenshot, or judge rationale.

5. Feedback generation should be incremental.
   - Rule modules, LLM judges, and VLM judges should emit small feedback fragments while
     scoring.
   - A final aggregator should merge, prioritize, deduplicate, and render those
     fragments.

## 3. Output artifacts

Each verifier run should eventually produce:

```text
<report_id>.eval.json
<report_id>.feedback.md
<report_id>.feedback.json
<report_id>.feedback.html        optional, for review dashboards
```

Batch runs should additionally produce:

```text
summary.json
summary.csv
feedback_summary.md
feedback_dashboard.html          optional
```

Recommended roles:

- `.feedback.md`: primary artifact for humans and agents.
- `.feedback.json`: compact structured backing data for automation.
- `.feedback.html`: visual inspection and dashboard review.
- `feedback_summary.md`: cross-sample themes, useful for skill-level iteration.

## 4. Reader model

### 4.1 Human expert

Needs:

- quickly judge whether the verifier's assessment is reasonable;
- inspect evidence behind high-impact critiques;
- identify verifier misalignment or over/under-penalization;
- compare reports and samples.

Design implications:

- show scores and gates, but also explain why;
- expose top evidence, not all raw internals;
- include “verifier uncertainty” and “alignment review needed” flags;
- provide links to chart crops, text spans, and judge rationales.

### 4.2 Human non-expert/operator

Needs:

- understand pass/fail and major problems;
- know whether a run is trustworthy;
- know whether failures are due to report quality, parser/runtime, missing resources,
  model errors, or verifier uncertainty.

Design implications:

- include plain-language summary;
- separate execution/parse failures from quality findings;
- use severity and priority labels;
- avoid requiring finance expertise for basic triage.

### 4.3 Agent

Needs:

- identify skill strengths and weaknesses;
- map feedback to generation skill components;
- propose concrete prompt/template/code changes;
- preserve evidence for review;
- avoid overfitting to one sample.

Design implications:

- every actionable item should include:
  - module;
  - issue type;
  - probable generation cause;
  - suggested skill patch;
  - acceptance criteria;
  - evidence refs;
  - confidence.

## 5. Feedback schema draft

The feedback schema should be compact enough to read and stable enough to automate.

### 5.1 Top-level object

```yaml
feedback_version: strategy_report_feedback_v0.1
verifier_mode: reference_based | candidate_only
report_id: string
input:
  candidate_path: string
  format: pdf | html | docx | text | unknown
  query: string | null
  reference_available: boolean
  profile_name: string
run_status:
  completed: boolean
  execution_failures: []
  parse_status: string
  evaluation_confidence: number
score_summary:
  overall_score: number
  grade: string
  gate_passed: boolean
  gate_failures: []
  dimension_scores: {}
reader_summary:
  one_paragraph: string
  strongest_aspects: []
  most_important_gaps: []
  verifier_uncertainties: []
priority_actions: []
module_feedback: []
evidence_index: []
agent_iteration_plan: {}
human_alignment_notes: {}
```

### 5.2 Priority action

This is the most important unit for skill iteration.

```yaml
id: action_001
priority: P0 | P1 | P2 | P3
audience: human | agent | both
category: content | structure | reasoning | visual | grounding | delivery | compliance | runtime
module_refs: [strategy_reasoning, visual_qa]
symptom: short readable statement
probable_cause: generation/template/model/parser cause, if known
recommended_skill_patch: concrete change to generation skill or prompt
acceptance_criteria: how to know the patch worked
evidence_refs: [evidence_001, chart_003]
confidence: 0.0-1.0
```

### 5.3 Module feedback

Module feedback keeps the connection to verifier internals without overwhelming the
reader.

```yaml
module: visual_qa
module_score: 0.81
status: pass | warn | fail | uncertain | skipped
plain_language_summary: string
strengths: []
gaps: []
actionable_items: [action_001]
judge_fragments: [fragment_001]
metrics:
  chart_count: 6
  vlm_judged_chart_count: 6
  visual_coverage_status: vlm_partially_judged
```

### 5.4 Judge feedback fragment

LLM/VLM/rule modules should emit fragments during scoring. The final feedback aggregator
should not have to infer everything from scores.

```yaml
fragment_id: fragment_001
source_module: chart_vlm_judge
source_type: rule | llm | vlm | parser | aggregator
target:
  type: chart | claim | section | document | layout | run
  id: chart_003
severity: blocker | high | medium | low | info
finding: string
rationale: string
suggested_fix: string
evidence_refs: []
confidence: 0.0-1.0
raw_score_refs:
  score: 0.42
  subscore: chart_text_alignment
```

### 5.5 Evidence reference

Evidence should be concise and linkable.

```yaml
evidence_id: evidence_001
type: text_span | chart_crop | context_image | full_page_image | module_metric | judge_rationale | source_fact
title: string
path: string | null
locator:
  chart_id: string | null
  section_id: string | null
  page: string | int | null
  char_start: int | null
  char_end: int | null
excerpt: short text
```

## 6. Human-facing Markdown layout

The Markdown artifact should not be a JSON pretty print. It should be designed as a
short review memo.

Proposed layout:

```text
# Feedback: <report_id>

## 1. Executive summary
- Overall judgement
- Gate / score / confidence
- Most important strengths
- Most important weaknesses

## 2. Priority actions for skill iteration
P0/P1/P2 actions with evidence and acceptance criteria.

## 3. Content and reasoning feedback
Structure, thesis, mechanism, evidence-to-conclusion, investment implications,
scenario/risk.

## 4. Visual and layout feedback
Visual coverage status, VLM findings, chart/text binding, source/unit/time-window
issues, HTML/rendering issues.

## 5. Grounding and factual feedback
For V1: reference coverage and factual/numeric correctness.
For candidate-only: claim discipline, numeric clarity, source note quality, uncertainty.

## 6. Verifier confidence and alignment review notes
Parse/runtime/model uncertainty and items that need human review.

## 7. Evidence appendix
Links to chart crops, text snippets, module metrics, and raw judge details.
```

## 7. V1 and candidate-only compatibility

### 7.1 Shared modules

Both modes can emit feedback for:

- structure;
- delivery/rendering;
- strategy reasoning;
- scenario/risk;
- visual QA;
- writing/layout;
- compliance;
- parse/runtime confidence.

### 7.2 V1-specific feedback

V1 has reference cases and should provide stronger feedback on:

- query satisfaction;
- coverage of required sections;
- preservation of key facts;
- numeric correctness against reference facts;
- source/reference alignment;
- omissions, contradictions, and overclaims;
- whether a model is failing because of reasoning, extraction, or generation style.

V1 feedback is especially useful for:

- skill iteration;
- model choice and model routing;
- diagnosing hallucination/coverage issues;
- calibrating verifier-human alignment.

### 7.3 Candidate-only/no-reference feedback

Candidate-only feedback should avoid pretending it knows factual truth beyond available
signals. It should focus on:

- whether the report looks like a professional strategy report;
- content density and specificity;
- strategy reasoning quality;
- risk/scenario completeness;
- claim discipline and numeric clarity;
- visual/layout quality;
- HTML parser/render robustness;
- visual coverage status and VLM review.

Candidate-only feedback is especially useful for:

- large-scale generation quality monitoring;
- agent-produced HTML iteration;
- fast comparison among candidate reports;
- surfacing visual/layout defects not visible from text-only scores.

## 8. Feedback generation pipeline

### 8.1 Current verifier pipeline

Current flow:

```text
input report
  -> parser / HTML adapter
  -> rule checks
  -> optional LLM/VLM judges
  -> scoring aggregation
  -> eval JSON / markdown / dashboard
```

### 8.2 Proposed feedback-aware pipeline

Proposed flow:

```text
input report
  -> parser / HTML adapter
       emits parse/runtime feedback fragments
  -> rule checks
       emit rule feedback fragments
  -> LLM/VLM judges
       emit rationale feedback fragments while judging
  -> scoring aggregation
       emits score/gate/confidence feedback fragments
  -> feedback aggregator
       normalizes, deduplicates, prioritizes, groups by skill action
  -> renderers
       feedback.md, feedback.json, feedback.html, batch feedback summary
```

### 8.3 Fragment emitters

Initial fragment emitters should include:

- parser / HTML adapter:
  - parse failure;
  - low-confidence body extraction;
  - browser fallback;
  - missing resources;
  - visual coverage status.
- structure module:
  - missing executive summary;
  - weak sectioning;
  - missing strategy/risk/disclaimer signals.
- strategy reasoning module:
  - weak thesis;
  - missing mechanism;
  - missing investment implication;
  - weak risk boundary.
- claim/numeric module:
  - weak units;
  - missing dates/time windows;
  - unclear claim discipline;
  - V1: missing/contradicted reference facts.
- visual QA module:
  - no visuals found;
  - visuals found but none scorable;
  - VLM promoted missed visual;
  - missing source/unit/time window;
  - poor chart-text binding;
  - crop/readability problems.
- compliance module:
  - redline issues;
  - overclaim/control problems.

### 8.4 Aggregator responsibilities

The feedback aggregator should:

1. normalize fragments into the shared schema;
2. deduplicate overlapping issues;
3. group findings by skill-level action;
4. assign priority and confidence;
5. separate report-quality issues from verifier/runtime uncertainty;
6. produce human-readable summaries;
7. preserve evidence refs;
8. emit both `.feedback.md` and `.feedback.json`.

### 8.5 Priority model

Priority should combine:

- severity;
- score impact;
- gate impact;
- confidence;
- recurrence across samples;
- relevance to generation skill changes.

Draft mapping:

- P0: blocks report usability or causes gate failure; clear skill fix exists.
- P1: materially lowers score or comparison quality; should be fixed soon.
- P2: useful improvement but not blocking.
- P3: low-priority polish or verifier uncertainty.

## 9. Integration points

### 9.1 V1 integration

Likely files:

- `run_eval.py`
- `checks.py`
- `claim_numeric_verifier.py`
- `strategy_reasoning_verifier.py`
- `chart_qa.py`
- `scoring.py`

V1 should call the shared feedback aggregator after `aggregate_scores`.

### 9.2 Candidate-only integration

Likely files:

- `run_eval_v2.py`
- `v2_checks.py`
- `v2_llm_verifiers.py`
- `chart_qa.py`
- `scoring_v2.py`
- `run_html_batch.py`

Candidate-only should call the same feedback aggregator after `aggregate_v2_scores`.

### 9.3 Shared package

Suggested directory:

```text
evals/strategy_report/feedback/
  FEEDBACK_DESIGN.md
  schema.py                  future
  fragments.py               future
  aggregator.py              future
  render_markdown.py         future
  render_html.py             future
  batch_summary.py           future
```

## 10. Initial implementation phases

### Phase 1: schema and renderer

- Define Python dataclasses or typed dictionaries for feedback fragments/actions.
- Build a renderer that produces readable Markdown from an in-memory feedback object.
- Generate `.feedback.md` and `.feedback.json` for candidate-only first, using existing
  module results.

### Phase 2: fragment emitters

- Add feedback fragments to:
  - parser/HTML adapter;
  - visual QA;
  - structure;
  - strategy reasoning;
  - claim/numeric.
- Preserve LLM/VLM rationale snippets as fragments.

### Phase 3: V1 support

- Add V1-specific reference coverage and factual grounding feedback.
- Ensure V1 and candidate-only share the same feedback renderer and action schema.

### Phase 4: batch-level feedback

- Aggregate recurring findings across samples.
- Produce `feedback_summary.md` for skill iteration.
- Add dashboards for priority actions and verifier-human alignment review.

## 11. Open design questions

1. Should `.feedback.md` be considered canonical, or should `.feedback.json` be
   canonical with Markdown as a rendering?
   - Current recommendation: JSON is canonical for automation, Markdown is canonical
     for review. They should be generated from the same feedback object.

2. How much LLM should be used in feedback aggregation?
   - Deterministic aggregation should handle priority, grouping, and evidence refs.
   - An optional LLM summarizer can rewrite human-facing prose, but should not invent
     findings.

3. How should feedback map to skill files?
   - Initial version can use `recommended_skill_patch` as prose.
   - Later version can add `skill_area` and `possible_file_or_prompt_targets`.

4. How should verifier-human alignment be represented?
   - Add explicit `alignment_review_needed` flags when confidence is low, VLM/rule
     disagree, or score impact is high but evidence is weak.

5. How should sample-level feedback become skill-level feedback?
   - Batch aggregator should cluster recurring actions and separate one-off sample
     defects from systemic skill defects.

## 12. Near-term recommendation

Implementation status, 2026-06-27:

- Shared deterministic feedback generation is implemented under
  `evals/strategy_report/feedback/`.
- V1/reference-based and candidate-only/no-reference runs both emit
  `<id>.feedback.md` and `<id>.feedback.json`.
- V1 `summary.json`, V2 `summary.json`, and HTML batch summaries include
  `feedback_markdown` and `feedback_json` paths.
- The first schema version is `strategy_report_feedback_v0.1`.
- The implemented artifact includes:
  - score summary;
  - human-readable reader summary;
  - runtime and parse notes, including VLM timing when available;
  - module feedback;
  - prioritized action items mapped to skill areas;
  - evidence index.
- The old candidate-only `.skill_feedback.md` path remains available as a legacy alias
  when `feedback.write_skill_feedback` is enabled, but it is rendered from the shared
  feedback object.

The next implementation step should be small:

1. Add shared feedback schema objects under `evals/strategy_report/feedback/`.
2. Build deterministic feedback aggregation from current v2 module results.
3. Render readable `.feedback.md`.
4. Keep `.skill_feedback.md` as an alias or legacy output during migration.
5. Then extend the same aggregator to V1.

This avoids turning feedback into another raw JSON dump while keeping it reliable enough
for agents to consume.
