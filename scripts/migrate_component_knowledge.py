from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


FIELDS = (
    "id",
    "label",
    "image_path",
    "component_type",
    "model",
    "definition",
    "standards",
    "aliases",
    "notes",
    "source",
    "dhash",
    "color_histogram",
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract the component-only knowledge base."
    )
    parser.add_argument("--source-knowledge", required=True)
    parser.add_argument("--output", default="data/index/components.json")
    args = parser.parse_args()

    source = Path(args.source_knowledge).resolve()
    output = Path(args.output).resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    components = [
        {field: item.get(field, [] if field in {"standards", "aliases", "color_histogram"} else "") for field in FIELDS}
        for item in payload.get("components", [])
        if isinstance(item, dict)
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    asset_dir = output.parent / "assets" / "components"
    asset_dir.mkdir(parents=True, exist_ok=True)
    for item in components:
        relative = Path(str(item["image_path"]))
        source_image = (
            relative if relative.is_absolute() else source.parent / relative
        )
        if not source_image.is_file():
            raise FileNotFoundError(source_image)
        target = output.parent / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_image, target)
    output.write_text(
        json.dumps(
            {"version": 1, "components": components},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "components": len(components),
                "asset_dir": str(asset_dir),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
