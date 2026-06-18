from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from electronic_recognition.image_index import image_features


STANDARD = "GB/T 4728.7-2022"
IEC_STANDARD = "IEC 60617"


FIXED_ENGLISH = {
    "S00305": "Operating device, general symbol; Relay coil, general symbol",
    "S00316": "Relay coil of an alternating current relay",
    "S00326": "Operating device of an electronic relay",
    "S00327": "Measuring relay; Device related to a measuring relay",
    "S00328": "Voltage failure to frame; Frame potential in case of fault",
    "S00335": "Current between neutrals of two polyphase systems",
    "S00337": "Inverse time-lag characteristic",
    "S00338": "No-voltage relay",
    "S00342": "Overcurrent relay",
    "S00343": "Overpower relay for reactive power",
    "S00348": "Divided-conductor detection relay",
    "S00351": "Overcurrent relay",
    "S00354": "Proximity sensor",
    "S00355": "Proximity sensing device",
    "S00356": "Proximity sensing capacitive",
    "S00357": "Touch sensor",
    "S00358": "Touch sensitive switch",
    "S00362": "Fuse, general symbol",
    "S00364": "Fuse; Striker fuse",
    "S00370": "Fuse switch-disconnector; On-load isolating fuse switch",
    "S00378": "Static switch, unidirectional",
    "S00379": "Static relay, general symbol",
    "S00384": "Coupling device with electrical separation, optical",
    "S01856": "Instrument multi-position selector switch for current circuit",
    "S01858": (
        "Instrument multi-position selector switch for voltage circuit "
        "with shown terminals"
    ),
    "S01911": "Break contact, delayed",
    "S01912": "Switch, manually operated, break contact",
}


FIXED_LABELS = {
    "S00305": "驱动器件一般符号；继电器线圈一般符号",
    "S00304": "带可控硅整流器的调节-启动器",
    "S01454": "复合开关，一般符号",
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Import GB/T 4728.7-2022 symbols from an OCR extraction "
            "preview generated from pages 31-50 and 51-68."
        )
    )
    parser.add_argument(
        "--extracted",
        default=str(
            PROJECT_ROOT
            / "tmp"
            / "pdfs"
            / "gbt47287-new-import"
            / "auto-preview2"
            / "extracted.json"
        ),
    )
    parser.add_argument(
        "--knowledge",
        default=str(PROJECT_ROOT / "data" / "index" / "components.json"),
    )
    args = parser.parse_args()

    extracted_path = Path(args.extracted).resolve()
    knowledge_path = Path(args.knowledge).resolve()
    asset_dir = knowledge_path.parent / "assets" / "components"
    asset_dir.mkdir(parents=True, exist_ok=True)

    extracted = json.loads(extracted_path.read_text(encoding="utf-8"))
    new_components: list[dict[str, object]] = []
    for item in extracted:
        model = str(item["id"])
        component_id = f"gbt47287-{model.lower()}"
        image_source = Path(str(item["image"]))
        if not image_source.is_absolute():
            image_source = PROJECT_ROOT / image_source
        image_target = asset_dir / f"{component_id}.png"
        _copy_clean_image(image_source, image_target)
        dhash, color_histogram = image_features(image_target)

        english = FIXED_ENGLISH.get(
            model, _clean_english(str(item.get("english", "")))
        )
        label = FIXED_LABELS.get(
            model, _clean_label(str(item.get("label", "")))
        )
        component_type = _clean_label(str(item.get("component_type", "")))
        shape_type = _clean_label(str(item.get("shape_type", "")))
        function_type = _clean_label(str(item.get("function_type", "")))
        application_type = _clean_label(
            str(item.get("application_type", ""))
        )

        aliases = [
            value
            for value in [
                model,
                english,
                *_split_terms(component_type),
                *_split_terms(shape_type),
                *_split_terms(function_type),
            ]
            if value
        ]
        new_components.append(
            {
                "id": component_id,
                "label": label,
                "image_path": f"assets/components/{image_target.name}",
                "component_type": component_type,
                "model": model,
                "definition": _definition(label, component_type, english),
                "standards": [STANDARD, IEC_STANDARD],
                "aliases": list(dict.fromkeys(aliases)),
                "notes": (
                    "内部使用的标准页面裁剪样本；元数据由页面 OCR "
                    "和人工校正整理，定义为识别用途的功能性归纳。"
                ),
                "source": (
                    f"{STANDARD}，PDF 分组 {item['prefix']}，"
                    f"PDF 第 {item['pdf_page']} 页，"
                    f"标准印刷页第 {item['printed_page']} 页，"
                    f"标准符号编号 {model}"
                ),
                "dhash": dhash,
                "color_histogram": color_histogram,
            }
        )

    payload = json.loads(knowledge_path.read_text(encoding="utf-8"))
    new_ids = {str(item["id"]) for item in new_components}
    existing = [
        item
        for item in payload.get("components", [])
        if str(item.get("id", "")) not in new_ids
    ]
    payload["version"] = 1
    payload["components"] = [*existing, *new_components]
    knowledge_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "knowledge": str(knowledge_path),
                "added_or_replaced": len(new_components),
                "component_count": len(payload["components"]),
                "asset_dir": str(asset_dir),
                "first_id": new_components[0]["id"]
                if new_components
                else None,
                "last_id": new_components[-1]["id"]
                if new_components
                else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _copy_clean_image(source: Path, target: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        image.convert("RGB").save(target, "PNG", optimize=True)


def _clean_label(value: str) -> str:
    value = value.replace(" - 般", "一般")
    value = value.replace(" - 启动器", "-启动器")
    value = value.replace("（ ", "（").replace(" ）", "）")
    value = value.replace(" ,", ",").replace(", ", ",")
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(
        r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", value
    )
    return value


def _clean_english(value: str) -> str:
    replacements = {
        "，": ",",
        "；": ";",
        "—": "-",
        " Of ": " of ",
        " a n ": " an ",
        " tO ": " to ",
        " tWO ": " two ",
        "C a S e": "case",
        "C)": "O",
        "()": "O",
        "l)": "D",
        "multl": "multi",
        "positlon": "position",
        "posltlon": "position",
        "clrctllt": "circuit",
        "devlce": "device",
        "sensltive": "sensitive",
        "svvitch": "switch",
        "capacltlve": "capacitive",
        "unidirectlonal": "unidirectional",
        "separatiomoptical": "separation, optical",
        "M1rror": "Mirror",
        "lnstrument": "Instrument",
        "Pr0X1m1ty": "Proximity",
        "Pr0X1mity": "Proximity",
        "S e n S O r": "sensor",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    value = re.sub(r"\s+", " ", value).strip()
    value = value.replace(" ,", ",").replace(" ;", ";")
    return value


def _split_terms(value: str) -> list[str]:
    if not value:
        return []
    return [
        item.strip()
        for item in re.split(r"[,;，；、]", value)
        if item.strip()
    ]


def _definition(label: str, component_type: str, english: str) -> str:
    if component_type:
        return (
            f"{label}，属于{component_type}类图形符号；"
            f"用于电气图纸中表示 {english}。"
        )
    return f"{label}，用于电气图纸中表示 {english}。"


if __name__ == "__main__":
    main()
