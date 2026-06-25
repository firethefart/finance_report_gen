from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


DEFAULT_PATHS = [
    "evals/strategy_report/profiles",
    "evals/strategy_report/*.py",
    "evals/strategy_report/results",
]


MOJIBAKE_MARKERS = [
    "锛",
    "涓",
    "浜",
    "閰",
    "璁",
    "寤",
    "棰",
    "鍊",
    "�",
]


EXPECTED_CHINESE = [
    "中文策略报告",
    "宏观",
    "政策",
    "产业链",
    "风险边界",
]


def iter_files(root: Path, patterns: list[str]) -> list[Path]:
    files: list[Path] = []
    for pattern in patterns:
        target = root / pattern
        if any(ch in pattern for ch in "*?[]"):
            files.extend(path for path in root.glob(pattern) if path.is_file())
        elif target.is_dir():
            files.extend(path for path in target.rglob("*") if path.is_file() and path.suffix.lower() in {".py", ".json", ".md", ".html", ".txt"})
        elif target.is_file():
            files.append(target)
    return sorted(set(files))


def audit_file(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return {"path": str(path), "ok": False, "error": f"utf8_decode_error: {exc}"}
    hits = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if is_detector_definition_line(line):
            continue
        for marker in MOJIBAKE_MARKERS:
            index = line.find(marker)
            if index >= 0:
                hits.append(
                    {
                        "line": line_no,
                        "marker": marker,
                        "context": line[max(0, index - 40) : index + 80],
                    }
                )
    return {
        "path": str(path),
        "ok": not hits,
        "mojibake_hits": hits,
    }


def is_detector_definition_line(line: str) -> bool:
    stripped = line.strip()
    if "MOJIBAKE_MARKERS" in stripped:
        return True
    if stripped.startswith("markers = [") and any(marker in stripped for marker in MOJIBAKE_MARKERS):
        return True
    if stripped in {f'"{marker}",' for marker in MOJIBAKE_MARKERS}:
        return True
    return False


def profile_probe(root: Path) -> dict:
    profile = root / "evals/strategy_report/profiles/full_best_effort.json"
    if not profile.exists():
        return {"ok": False, "error": "profile_missing"}
    data = json.loads(profile.read_text(encoding="utf-8"))
    blob = json.dumps(data.get("strategy_reasoning", {}), ensure_ascii=False)
    return {
        "ok": all(term in blob for term in EXPECTED_CHINESE),
        "expected_terms_present": {term: term in blob for term in EXPECTED_CHINESE},
        "mojibake_present": any(marker in blob for marker in MOJIBAKE_MARKERS),
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Audit UTF-8 and mojibake risks in strategy verifier files.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--path", action="append", dest="paths", help="Path or glob relative to root. Can be repeated.")
    args = parser.parse_args()

    root = args.root.resolve()
    files = iter_files(root, args.paths or DEFAULT_PATHS)
    rows = [audit_file(path) for path in files]
    failures = [row for row in rows if not row["ok"]]
    result = {
        "root": str(root),
        "file_count": len(rows),
        "failure_count": len(failures),
        "profile_probe": profile_probe(root),
        "failures": failures[:50],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if failures or not result["profile_probe"]["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
