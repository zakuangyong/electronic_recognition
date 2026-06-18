from __future__ import annotations

import json

from .models import ComponentSample


SYSTEM_PROMPT = """你是电气图纸元器件识别助手。
只依据待识别图纸、知识库目录和参考图片判断，不虚构图纸中不存在的元件。
所有坐标统一使用页面左上角为原点的0至1000归一化坐标。"""


def catalog_prompt(
    text: str,
    catalog: list[dict[str, object]],
    limit: int,
) -> str:
    return f"""从组件知识库目录中选择最可能出现在待识别图纸中的候选项。

知识库目录：
{json.dumps(catalog, ensure_ascii=False)}

图纸文本层：
{text[:30000]}

要求：
1. 结合图纸视觉、文字代号、名称和功能选择候选；
2. 最多返回{limit}个candidate_ids；
3. candidate_ids只能使用目录中的id；
4. 不做最终识别，不输出图纸中不存在的确定结论。

严格输出JSON：
{{
  "candidate_ids": ["知识库id"],
  "reason": "简短说明"
}}"""


def recognition_prompt(
    text: str,
    references: list[ComponentSample],
    page_views: list[dict[str, object]],
    page_number: int,
) -> str:
    reference_metadata = [
        {
            "input_image_index": len(page_views) + index + 1,
            "id": sample.id,
            "label": sample.label,
            "component_type": sample.component_type,
            "model": sample.model,
            "definition": sample.definition,
            "aliases": sample.aliases,
            "orientation_note": (
                "该参考图是方向样本面板，包含原图及其"
                "0/90/180/270度方向，可能还包含人工方向样本。"
            ),
        }
        for index, sample in enumerate(references)
    ]
    return f"""识别电气图纸中的元器件和图形标识。

当前识别页：第{page_number}页

待识别图片元数据：
{json.dumps(page_views, ensure_ascii=False)}

参考图片元数据：
{json.dumps(reference_metadata, ensure_ascii=False)}

图片顺序：
1. 前{len(page_views)}张是同一图纸页面的整页图和重叠切片；
2. 待识别图片的bounds_in_page表示它在原始页面0至1000坐标中的范围；
3. 后续图片按参考图片元数据中的input_image_index对应知识库参考图；
4. 参考图片只用于比对，绝不能当作图纸内容。

图纸文本层：
{text[:30000]}

要求：
1. 必须比较参考面板中的所有横向、竖向和反向版本，允许旋转、缩放、线宽变化和邻近线路干扰；
2. 同一种元件如果来自不同source_image_index，可以分多条输出，系统会在原图坐标中合并去重；
3. occurrence_count为当前输出条目中的实例数量；
4. source_image_index填写发现该实例的待识别图片序号，优先采用切片中更清晰的结果；
5. regions使用source_image_index对应图片的局部坐标，列出每个实例的[x0,y0,x1,y1]边界框，归一化到0至1000；
6. 同一实例在整页图和切片中重复出现时只输出一次；
7. occurrence_count应与regions数量一致；
8. code填写邻近代号；多个代号用逗号分隔；
9. 无可靠证据时不得输出。

严格输出JSON：
{{
  "detected_components": [
    {{
      "reference_id": "知识库id",
      "label": "元件名称",
      "code": "图纸代号或空字符串",
      "component_type": "元件类别",
      "page": {page_number},
      "source_image_index": 2,
      "occurrence_count": 1,
      "confidence": 0.0,
      "regions": [[0, 0, 1000, 1000]],
      "evidence": "邻近文字或视觉证据"
    }}
  ],
  "warnings": []
}}"""
