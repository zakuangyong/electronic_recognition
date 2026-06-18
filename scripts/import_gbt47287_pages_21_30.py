from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import fitz
from PIL import Image, ImageOps


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from electronic_recognition.image_index import image_features


RENDER_DPI = 300
REFERENCE_WIDTH = 1819
REFERENCE_HEIGHT = 2573


COMPONENTS = [
    {
        "model": "S00271",
        "page": 1,
        "crop": (445, 475, 810, 680),
        "label": "多位开关，最多四位",
        "component_type": "多位置开关",
        "definition": "具有最多四个稳定选择位置，并按所选位置切换触点连接关系的开关。",
        "aliases": [
            "Multi-position switch, maximum four positions",
            "多位选择开关",
            "四位开关",
        ],
    },
    {
        "model": "S00272",
        "page": 1,
        "crop": (445, 1360, 820, 1570),
        "label": "带位置图示的多位开关",
        "component_type": "多位置开关",
        "definition": "用位置图示表达各选择位置与触点连接关系的多位开关。",
        "aliases": [
            "Multi-position switch, with position diagram",
            "位置图示多位开关",
            "多档转换开关",
        ],
    },
    {
        "model": "S00284",
        "page": 2,
        "crop": (455, 480, 650, 665),
        "label": "接触器；接触器的主闭合触点",
        "component_type": "接触器",
        "definition": "接触器处于动作状态时闭合、用于主电路通断的主触点。",
        "aliases": [
            "Contactor",
            "Main make contact of a contactor",
            "接触器主闭合触点",
            "主常开触点",
        ],
    },
    {
        "model": "S00285",
        "page": 2,
        "crop": (455, 1370, 650, 1605),
        "label": "带自动释放功能的接触器",
        "component_type": "接触器",
        "definition": "带有自动脱扣或自动释放机构的接触器。",
        "aliases": [
            "Contactor with automatic tripping",
            "自动脱扣接触器",
            "自动释放接触器",
        ],
    },
    {
        "model": "S00286",
        "page": 3,
        "crop": (455, 480, 650, 665),
        "label": "接触器；接触器的主断触点",
        "component_type": "接触器",
        "definition": "接触器处于动作状态时断开、用于主电路通断的主触点。",
        "aliases": [
            "Contactor",
            "Main break contact of a contactor",
            "接触器主断触点",
            "主常闭触点",
        ],
    },
    {
        "model": "S00287",
        "page": 3,
        "crop": (455, 1370, 650, 1605),
        "label": "断路器",
        "component_type": "开关和保护器件",
        "definition": "能接通、承载和分断正常电流，并在异常条件下自动分断电路的机械开关器件。",
        "aliases": ["Circuit breaker", "自动开关", "QF"],
    },
    {
        "model": "S00288",
        "page": 4,
        "crop": (455, 480, 650, 665),
        "label": "隔离器",
        "component_type": "隔离开关",
        "definition": "在断开位置提供规定隔离距离、用于使电路或设备与电源隔离的开关器件。",
        "aliases": ["Disconnector", "Isolator", "隔离开关"],
    },
    {
        "model": "S00289",
        "page": 4,
        "crop": (455, 1360, 780, 1570),
        "label": "双位隔离器",
        "component_type": "隔离开关",
        "definition": "具有两个可选择隔离位置，并可在中间位置断开的隔离器。",
        "aliases": [
            "Two-way disconnector",
            "Two-way isolator",
            "双向隔离器",
            "双位隔离开关",
        ],
    },
    {
        "model": "S00290",
        "page": 5,
        "crop": (455, 480, 650, 665),
        "label": "隔离开关；负荷隔离开关",
        "component_type": "负荷隔离开关",
        "definition": "兼具负荷电流开断能力和隔离功能的机械开关器件。",
        "aliases": [
            "Switch-disconnector",
            "On-load isolating switch",
            "负荷开关",
        ],
    },
    {
        "model": "S00291",
        "page": 5,
        "crop": (455, 1360, 650, 1560),
        "label": "带自动释放功能的负荷隔离开关",
        "component_type": "负荷隔离开关",
        "definition": "兼具负荷隔离功能，并能由内装脱扣器自动释放的开关器件。",
        "aliases": [
            "Switch-disconnector, automatic release",
            "On-load isolating switch, automatic release",
            "自动脱扣负荷隔离开关",
        ],
    },
    {
        "model": "S00292",
        "page": 6,
        "crop": (445, 475, 815, 675),
        "label": "隔离器",
        "component_type": "隔离开关",
        "definition": "带有手工操作装置、用于在断开位置实现电路隔离的机械开关器件。",
        "aliases": ["Disconnector", "Isolator", "手动隔离器", "手动隔离开关"],
    },
    {
        "model": "S00293",
        "page": 6,
        "crop": (455, 1370, 650, 1515),
        "label": "自由脱扣机构",
        "component_type": "脱扣机构",
        "definition": "即使操作件保持在合闸位置，脱扣后仍能使触点可靠分断的机械机构。",
        "aliases": ["Trip-free mechanism", "自由脱扣", "脱扣机构"],
    },
    {
        "model": "S00294",
        "page": 7,
        "crop": (450, 470, 930, 915),
        "label": "自由脱扣机构，应用",
        "component_type": "开关装置组合",
        "definition": "自由脱扣机构在三极机械式开关装置中的组合应用示例。",
        "aliases": [
            "Trip-free mechanism, application",
            "自由脱扣机构应用",
            "三极开关自由脱扣机构",
        ],
    },
    {
        "model": "S00295",
        "page": 7,
        "crop": (450, 1960, 1100, 2410),
        "label": "三极机械式开关装置",
        "component_type": "开关装置组合",
        "definition": "三个主极机械联动，并可配合脱扣器、线圈和辅助触点工作的开关装置。",
        "aliases": [
            "Mechanical switching device, three-pole",
            "三极机械开关",
            "三极开关装置",
        ],
    },
    {
        "model": "S00296",
        "page": 8,
        "crop": (430, 1460, 875, 1705),
        "label": "正向断开开关",
        "component_type": "正向操作开关",
        "definition": "通过直接机械作用保证主动断触点可靠断开的开关。",
        "aliases": [
            "Switch with positive opening",
            "强制断开开关",
            "正向操作开关",
        ],
    },
    {
        "model": "S00297",
        "page": 9,
        "crop": (455, 475, 650, 690),
        "label": "电动机启动器，一般符号",
        "component_type": "电动机启动器",
        "definition": "用于电动机启动、停止和必要保护功能的启动器一般图形符号。",
        "aliases": ["Motor starter, general symbol", "电机启动器", "motor starter"],
    },
    {
        "model": "S00298",
        "page": 9,
        "crop": (455, 1360, 650, 1540),
        "label": "步进启动器",
        "component_type": "电动机启动器",
        "definition": "按预定级次逐步改变启动条件的电动机启动器。",
        "aliases": ["Starter operating in steps", "分级启动器", "逐级启动器"],
    },
    {
        "model": "S00299",
        "page": 10,
        "crop": (430, 470, 650, 655),
        "label": "调节-启动器",
        "component_type": "电动机启动器",
        "definition": "兼具电动机启动和运行参数调节功能的启动器。",
        "aliases": ["Starter-regulator", "调节启动器", "起动调节器"],
    },
    {
        "model": "S00301",
        "page": 10,
        "crop": (430, 1340, 650, 1505),
        "label": "可逆直接在线启动器",
        "component_type": "电动机启动器",
        "definition": "可改变电动机相序或连接方向，实现正反转的直接在线启动器。",
        "aliases": [
            "Direct-on-line starter, reversing",
            "可逆直接启动器",
            "正反转启动器",
        ],
    },
    {
        "model": "S00302",
        "page": 10,
        "crop": (430, 2100, 650, 2300),
        "label": "星-三角启动器",
        "component_type": "电动机启动器",
        "definition": "启动时采用星形连接、运行时切换为三角形连接的降压启动器。",
        "aliases": ["Star-delta starter", "星三角启动器", "Y-Δ启动器"],
    },
]


def _scaled_crop(
    image: Image.Image, crop: tuple[int, int, int, int]
) -> Image.Image:
    scale_x = image.width / REFERENCE_WIDTH
    scale_y = image.height / REFERENCE_HEIGHT
    box = (
        round(crop[0] * scale_x),
        round(crop[1] * scale_y),
        round(crop[2] * scale_x),
        round(crop[3] * scale_y),
    )
    cropped = image.crop(box).convert("RGB")
    grayscale = ImageOps.grayscale(cropped)
    foreground = grayscale.point(lambda value: 255 if value < 245 else 0)
    bounds = foreground.getbbox()
    if not bounds:
        raise ValueError(f"No symbol pixels found in crop {crop}")
    padding = 10
    left = max(0, bounds[0] - padding)
    top = max(0, bounds[1] - padding)
    right = min(cropped.width, bounds[2] + padding)
    bottom = min(cropped.height, bounds[3] + padding)
    return cropped.crop((left, top, right, bottom))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import GB/T 4728.7-2022 symbols from printed pages 21-30."
    )
    parser.add_argument("pdf")
    parser.add_argument(
        "--knowledge",
        default=str(PROJECT_ROOT / "data" / "index" / "components.json"),
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf).resolve()
    knowledge_path = Path(args.knowledge).resolve()
    asset_dir = knowledge_path.parent / "assets" / "components"
    asset_dir.mkdir(parents=True, exist_ok=True)

    document = fitz.open(pdf_path)
    if len(document) != 10:
        raise ValueError(f"Expected 10 PDF pages, got {len(document)}")

    rendered: dict[int, Image.Image] = {}
    matrix = fitz.Matrix(RENDER_DPI / 72, RENDER_DPI / 72)
    for page_number in range(1, 11):
        pixmap = document[page_number - 1].get_pixmap(
            matrix=matrix, alpha=False
        )
        rendered[page_number] = Image.frombytes(
            "RGB", (pixmap.width, pixmap.height), pixmap.samples
        )

    new_components: list[dict[str, object]] = []
    for item in COMPONENTS:
        model = str(item["model"])
        component_id = f"gbt47287-{model.lower()}"
        image_path = asset_dir / f"{component_id}.png"
        symbol = _scaled_crop(
            rendered[int(item["page"])],
            item["crop"],
        )
        symbol.save(image_path, "PNG", optimize=True)
        dhash, color_histogram = image_features(image_path)
        new_components.append(
            {
                "id": component_id,
                "label": item["label"],
                "image_path": f"assets/components/{image_path.name}",
                "component_type": item["component_type"],
                "model": model,
                "definition": item["definition"],
                "standards": ["GB/T 4728.7-2022", "IEC 60617"],
                "aliases": [model, *item["aliases"]],
                "notes": (
                    "内部使用的标准页面裁剪样本；保留原符号点阵边界，"
                    "元数据为识别用途的功能性归纳。"
                ),
                "source": (
                    f"{pdf_path.name}，PDF 第 {item['page']} 页，"
                    f"标准印刷页第 {20 + int(item['page'])} 页，"
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
                "pdf": str(pdf_path),
                "knowledge": str(knowledge_path),
                "added_or_replaced": len(new_components),
                "component_count": len(payload["components"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
