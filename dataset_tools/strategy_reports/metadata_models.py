from __future__ import annotations

from typing import Any, Literal

from ftfy import fix_text
from pydantic import BaseModel, ConfigDict, Field, field_validator


BusinessType = Literal[
    "asset_manager",
    "investment_bank",
    "private_bank",
    "brokerage",
    "research_provider",
    "regulator",
    "exchange",
    "other",
]
QualityTier = Literal["A", "B", "C", "Reject"]


class FlexibleModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class SourcePdf(FlexibleModel):
    file_path: str
    file_name: str
    sha256: str | None = None
    file_size_bytes: int = 0
    page_count: int = 0
    parse_method: str = "unknown"
    parse_quality: str = "unknown"


class Institution(FlexibleModel):
    name: str
    business_type: BusinessType | str = "other"
    country_or_region: str | None = None
    official_url: str | None = None


class CandidateQuery(FlexibleModel):
    query: str
    language: Literal["zh", "en", "mixed"] | str = "en"
    query_style: str = "analyst_request"
    scope_constraints: list[str] = Field(default_factory=list)


class ExpectedReportType(FlexibleModel):
    type: str
    depth: str = "institutional_style"
    output_format: str = "webpage"
    expected_time_horizon: str | None = None
    target_reader: str | None = None


class SourcePackItem(FlexibleModel):
    name: str
    type: str = "primary_report_pdf"
    url_or_path: str | None = None
    date: str | None = None
    required: bool = True
    observed_in_pdf: bool = True
    notes: str = ""


class KeyFactItem(FlexibleModel):
    fact_id: str
    claim: str
    fact_type: str = "other"
    value: str | None = None
    unit: str | None = None
    time_window: str | None = None
    source_ref: str
    confidence: float = 0.5
    why_it_matters: str
    verification_hint: str


class MustHaveSectionItem(FlexibleModel):
    section_name: str
    required: bool = True
    purpose: str
    required_points: list[str] = Field(default_factory=list)
    evaluation_focus: str


class ProhibitedMistakeItem(FlexibleModel):
    mistake: str
    severity: str = "medium"
    why_it_matters: str
    related_eval_dimension: str = "facts"


class ExtractionConfidence(FlexibleModel):
    overall: float = 0.5
    classification: float = 0.5
    key_facts: float = 0.5
    source_pack: float = 0.5
    query: float = 0.5


class StrategyMetadataCase(FlexibleModel):
    case_id: str
    source_pdf: SourcePdf
    institution: Institution
    report_title: str
    report_date: str | None = None
    publication_period: str | None = None
    authors_or_team: list[str] = Field(default_factory=list)
    strategy_subtype: str
    secondary_tags: list[str] = Field(default_factory=list)
    classification_rationale: str
    quality_tier: QualityTier | str
    quality_rationale: str
    candidate_query: CandidateQuery
    expected_report_type: ExpectedReportType
    source_pack: list[SourcePackItem] = Field(default_factory=list)
    key_facts: list[KeyFactItem] = Field(default_factory=list)
    must_have_sections: list[MustHaveSectionItem] = Field(default_factory=list)
    prohibited_mistakes: list[ProhibitedMistakeItem] = Field(default_factory=list)
    reference_notes: dict[str, Any] = Field(default_factory=dict)
    charts_and_tables_to_learn_from: list[dict[str, Any]] = Field(default_factory=list)
    evaluation_hooks: dict[str, Any] = Field(default_factory=dict)
    extraction_confidence: ExtractionConfidence = Field(default_factory=ExtractionConfidence)
    extraction_notes: str = ""

    @field_validator("key_facts")
    @classmethod
    def limit_key_facts(cls, value: list[KeyFactItem]) -> list[KeyFactItem]:
        return value[:12]


def validate_case(data: dict[str, Any]) -> tuple[bool, dict[str, Any], list[str]]:
    data = normalize_case(data)
    try:
        model = StrategyMetadataCase.model_validate(data)
        return True, model.model_dump(mode="json"), []
    except Exception as exc:  # noqa: BLE001
        return False, data, [repr(exc)]


def normalize_case(data: dict[str, Any]) -> dict[str, Any]:
    data = fix_strings(dict(data))
    data.setdefault("candidate_query", default_candidate_query(data))
    data.setdefault("expected_report_type", default_expected_report_type(data))
    data["source_pack"] = [normalize_source_pack_item(item) for item in data.get("source_pack") or []]
    data["key_facts"] = [normalize_key_fact_item(item, index) for index, item in enumerate(data.get("key_facts") or [], start=1)]
    data["must_have_sections"] = [
        normalize_must_have_item(item) for item in data.get("must_have_sections") or []
    ]
    data["prohibited_mistakes"] = [
        normalize_prohibited_item(item) for item in data.get("prohibited_mistakes") or []
    ]
    data["charts_and_tables_to_learn_from"] = [
        normalize_chart_item(item) for item in data.get("charts_and_tables_to_learn_from") or []
    ]
    return data


def fix_strings(value: Any) -> Any:
    if isinstance(value, str):
        text = fix_text(value)
        replacements = {
            "鈥?": "-",
            "鈥檚": "'s",
            "鈥檛": "'t",
            "鈥檙": "'r",
            "鈥渟": '"s',
            "鈥渢": '"t',
            "鈥�": "-",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text
    if isinstance(value, list):
        return [fix_strings(item) for item in value]
    if isinstance(value, dict):
        return {key: fix_strings(item) for key, item in value.items()}
    return value


def default_candidate_query(data: dict[str, Any]) -> dict[str, Any]:
    title = data.get("report_title") or "this strategy report"
    subtype = data.get("strategy_subtype") or "strategy_report"
    return {
        "query": f"What are the main conclusions and investment implications of {title}?",
        "language": "en",
        "query_style": "analyst_request",
        "scope_constraints": [str(subtype)],
    }


def default_expected_report_type(data: dict[str, Any]) -> dict[str, Any]:
    subtype = data.get("strategy_subtype") or "strategy_report"
    horizon = data.get("publication_period")
    return {
        "type": str(subtype),
        "depth": "institutional_style",
        "output_format": "webpage",
        "expected_time_horizon": horizon,
        "target_reader": "strategy report benchmark evaluator",
    }


def normalize_source_pack_item(item: Any) -> dict[str, Any]:
    if isinstance(item, str):
        return {"name": item, "type": "other", "notes": "Source candidate inferred from report content."}
    if not isinstance(item, dict):
        return {"name": str(item), "type": "other", "notes": ""}
    item = dict(item)
    item.setdefault("name", item.get("source_id") or item.get("title") or item.get("description") or "source_candidate")
    item.setdefault("type", item.get("source_type") or "other")
    item.setdefault("url_or_path", item.get("url") or item.get("path"))
    item.setdefault("date", None)
    item.setdefault("required", True)
    item.setdefault("observed_in_pdf", True)
    item.setdefault("notes", item.get("description") or item.get("verification_hint") or "")
    return item


def normalize_key_fact_item(item: Any, index: int) -> dict[str, Any]:
    if isinstance(item, str):
        item = {"claim": item}
    elif isinstance(item, dict):
        item = dict(item)
    else:
        item = {"claim": str(item)}
    item.setdefault("fact_id", f"fact_{index:03d}")
    item.setdefault("claim", item.get("fact") or item.get("description") or "")
    item.setdefault("fact_type", item.get("type") or "other")
    item.setdefault("value", None)
    item.setdefault("unit", None)
    item.setdefault("time_window", None)
    item.setdefault("source_ref", item.get("source") or item.get("source_id") or "source_report_excerpt")
    item.setdefault("confidence", 0.6)
    item.setdefault("why_it_matters", item.get("rationale") or item.get("importance") or "Important benchmark fact from the source report.")
    item.setdefault("verification_hint", item.get("verify") or item.get("source_ref") or "Verify against the source report excerpt and original report.")
    return item


def normalize_must_have_item(item: Any) -> dict[str, Any]:
    if isinstance(item, str):
        item = {"section_name": item}
    elif isinstance(item, dict):
        item = dict(item)
    else:
        item = {"section_name": str(item)}
    item.setdefault("required", True)
    item.setdefault("purpose", item.get("description") or "Required section for this strategy report subtype.")
    item.setdefault("required_points", item.get("points") or [])
    item.setdefault("evaluation_focus", item.get("focus") or item.get("description") or "Check coverage, specificity, and source grounding.")
    return item


def normalize_prohibited_item(item: Any) -> dict[str, Any]:
    if isinstance(item, str):
        item = {"mistake": item}
    elif isinstance(item, dict):
        item = dict(item)
    else:
        item = {"mistake": str(item)}
    item.setdefault("severity", item.get("level") or "medium")
    item.setdefault("why_it_matters", item.get("reason") or "This would materially reduce benchmark answer quality.")
    item.setdefault("related_eval_dimension", item.get("dimension") or "facts")
    return item


def normalize_chart_item(item: Any) -> dict[str, Any]:
    if isinstance(item, str):
        return {"title_or_description": item, "type": "other", "why_exemplary": "", "data_or_source_note": None, "expected_eval_use": "chart_logic"}
    if isinstance(item, dict):
        item = dict(item)
    else:
        item = {"title_or_description": str(item)}
    item.setdefault("title_or_description", item.get("chart_name") or item.get("description") or item.get("title") or "chart_or_table")
    item.setdefault("type", item.get("chart_type") or "other")
    item.setdefault("why_exemplary", item.get("why") or "")
    item.setdefault("data_or_source_note", item.get("source") or item.get("data_note"))
    item.setdefault("expected_eval_use", item.get("eval_use") or "chart_logic")
    return item
