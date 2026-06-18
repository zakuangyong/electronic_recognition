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
    drawing_page_count: int,
) -> str:
    metadata = [
        {
            "reference_image_index": index + 1,
            "id": sample.id,
            "label": sample.label,
            "component_type": sample.component_type,
            "model": sample.model,
            "definition": sample.definition,
            "aliases": sample.aliases,
        }
        for index, sample in enumerate(references)
    ]
    return f"""识别电气图纸中的元器件和图形标识。

参考图片元数据：
{json.dumps(metadata, ensure_ascii=False)}

图片顺序：
1. 第1至第{drawing_page_count}张是待识别图纸页面；
2. 后续图片按reference_image_index顺序对应知识库参考图片；
3. 参考图片只用于比对，绝不能当作图纸内容。

图纸文本层：
{text[:30000]}

要求：
1. 允许旋转、缩放、线宽变化和邻近线路干扰；
2. 同一种元件在同一页只输出一条；
3. occurrence_count为该页实例数量；
4. regions列出每个实例的[x0,y0,x1,y1]边界框，坐标归一化到0至1000；
5. occurrence_count应与regions数量一致；
6. code填写邻近代号；多个代号用逗号分隔；
7. 无可靠证据时不得输出。

严格输出JSON：
{{
  "detected_components": [
    {{
      "reference_id": "知识库id",
      "label": "元件名称",
      "code": "图纸代号或空字符串",
      "component_type": "元件类别",
      "page": 1,
      "occurrence_count": 1,
      "confidence": 0.0,
      "regions": [[0, 0, 1000, 1000]],
      "evidence": "邻近文字或视觉证据"
    }}
  ],
  "warnings": []
}}"""
