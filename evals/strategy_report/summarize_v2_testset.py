from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


GROUP_FIELDS = ("format", "language", "archetype", "subtype")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_rows(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(field) or "unknown")].append(row)

    summaries = []
    for value, members in sorted(groups.items()):
        dimensions = sorted(
            {
                dimension
                for member in members
                for dimension in (member.get("dimension_score_normalized") or {})
            }
        )
        summaries.append(
            {
                field: value,
                "count": len(members),
                "average_score": round(mean(float(member["overall_score"]) for member in members), 2),
                "minimum_score": round(min(float(member["overall_score"]) for member in members), 2),
                "maximum_score": round(max(float(member["overall_score"]) for member in members), 2),
                "gate_pass_count": sum(bool(member.get("gate_passed")) for member in members),
                "gate_pass_rate": round(
                    sum(bool(member.get("gate_passed")) for member in members) / len(members),
                    3,
                ),
                "average_dimensions": {
                    dimension: round(
                        mean(
                            float((member.get("dimension_score_normalized") or {}).get(dimension, 0.0))
                            for member in members
                        ),
                        3,
                    )
                    for dimension in dimensions
                },
            }
        )
    return summaries


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Candidate-Only Verifier Core Test-Set Layered Summary",
        "",
        f"- Source: `{summary['source_summary']}`",
        f"- Completed: {summary['completed_count']}/{summary['requested_count']}",
        f"- Report-level failures: {summary['failure_count']}",
        "",
    ]
    for field in GROUP_FIELDS:
        lines.extend(
            [
                f"## By {field}",
                "",
                f"| {field} | Count | Average | Min | Max | Gate pass |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in summary["groups"][field]:
            lines.append(
                f"| {row[field]} | {row['count']} | {row['average_score']:.2f} | "
                f"{row['minimum_score']:.2f} | {row['maximum_score']:.2f} | "
                f"{row['gate_pass_count']}/{row['count']} ({row['gate_pass_rate']:.1%}) |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize a V2 core-test-set run by key test dimensions.")
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-md", type=Path, required=True)
    args = parser.parse_args()

    source = read_json(args.summary)
    rows = source.get("results") or []
    result = {
        "source_summary": str(args.summary),
        "requested_count": source.get("requested_count", len(rows)),
        "completed_count": source.get("completed_count", len(rows)),
        "failure_count": source.get("failure_count", 0),
        "groups": {field: summarize_rows(rows, field) for field in GROUP_FIELDS},
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    args.out_md.write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps({key: result[key] for key in ["requested_count", "completed_count", "failure_count"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
