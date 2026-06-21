from __future__ import annotations

import argparse
import json
from pathlib import Path

from electronic_recognition.combination_rules import detect_combinations


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate combination rules against saved recognition results."
    )
    parser.add_argument("results", nargs="+", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    reports = [_analyze(path) for path in args.results]
    if args.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
        return
    for report in reports:
        print(f"\n{report['document']} ({report['result_dir']})")
        if not report["combinations"]:
            print("  未匹配到组合规则")
            continue
        for item in report["combinations"]:
            print(
                f"  [{item['rule_id']}] {item['name']} "
                f"{item['group_code']} ({item['confidence']:.0%})"
            )


def _analyze(path: Path) -> dict[str, object]:
    result_dir = path if path.is_dir() else path.parent
    result_path = result_dir / "result.json" if path.is_dir() else path
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    steps = payload.get("recognition_steps", {})
    combinations = detect_combinations(
        payload.get("detected_components", []),
        open_symbols=(
            steps.get("open_symbols", [])
            if isinstance(steps, dict)
            else []
        ),
        component_table=payload.get("component_table", {}),
        title_block=payload.get("title_block", {}),
        control_signal_configuration=payload.get(
            "control_signal_configuration", {}
        ),
    )
    return {
        "result_dir": str(result_dir),
        "document": payload.get("document", result_dir.name),
        "combinations": combinations,
    }


if __name__ == "__main__":
    main()
