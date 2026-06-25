from __future__ import annotations

import unittest
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from checks import compliance_redline_check, number_preservation, section_coverage_check
from scoring import aggregate_scores


class StrategyReportEvalUnitTests(unittest.TestCase):
    def test_number_preservation_handles_percent_and_commas(self) -> None:
        self.assertEqual(number_preservation(["40%", "1,250"], ["40 %", "1250"]), 1.0)

    def test_compliance_redline_blocks_guarantee_wording(self) -> None:
        result = compliance_redline_check({}, {"text": "This product offers guaranteed return and is risk-free."})
        self.assertLess(result["score"], 0.7)
        self.assertTrue(result["redline_issues"])

    def test_section_coverage_uses_must_have_sections(self) -> None:
        case = {
            "must_have_sections": [
                {"section_name": "Executive summary", "required": True},
                {"section_name": "Risk factors", "required": True},
            ]
        }
        parsed = {
            "headings": ["Executive summary", "Risk factors"],
            "text": "Executive summary\nKey thesis.\nRisk factors\nPolicy and market uncertainty.",
        }
        result = section_coverage_check(case, parsed)
        self.assertGreaterEqual(result["score"], 0.8)
        self.assertFalse(result["issues"])

    def test_aggregate_rejects_redline(self) -> None:
        case = {"case_id": "unit", "source_document": {"file_path": "a.pdf"}}
        parsed = {"path": "a.pdf"}
        module = {"score": 1.0, "issues": []}
        rule_results = {
            "render_delivery": module,
            "section_coverage": module,
            "source_quality": module,
            "claim_citation_alignment": module,
            "numeric_entity_consistency": module,
            "strategy_reasoning_rule": module,
            "scenario_risk": module,
            "chart_qa": module,
            "compliance_redline": {
                "score": 0.2,
                "issues": [{"issue_type": "compliance_issue", "severity": "blocker", "location": "redline", "description": "bad"}],
                "redline_issues": [{"issue_type": "compliance_issue", "severity": "blocker", "location": "redline", "description": "bad"}],
            },
        }
        result = aggregate_scores(case, parsed, rule_results)
        self.assertEqual(result["grade"], "Reject")
        self.assertIn("redline_issue_present", result["gate"]["failures"])


if __name__ == "__main__":
    unittest.main()
