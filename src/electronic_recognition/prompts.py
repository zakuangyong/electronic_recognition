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
1. 前{len(page_views)}张是当前图纸页面的整页图；
2. 待识别图片的bounds_in_page表示它在原始页面0至1000坐标中的范围；
3. 后续图片按参考图片元数据中的input_image_index对应知识库参考图；
4. 参考图片只用于比对，绝不能当作图纸内容。

图纸文本层：
{text[:30000]}

要求：
1. 必须比较参考面板中的所有横向、竖向和反向版本，允许旋转、缩放、线宽变化和邻近线路干扰；
2. 同一种元件如果来自不同source_image_index，可以分多条输出，系统会在原图坐标中合并去重；
3. occurrence_count为当前输出条目中的实例数量；
4. source_image_index填写发现该实例的待识别整页图片序号；
5. regions使用source_image_index对应图片的局部坐标，列出每个实例的[x0,y0,x1,y1]边界框，归一化到0至1000；
6. 同一实例只输出一次，不要重复计数；
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
      "source_image_index": 1,
      "occurrence_count": 1,
      "confidence": 0.0,
      "regions": [[0, 0, 1000, 1000]],
      "evidence": "邻近文字或视觉证据"
    }}
  ],
  "warnings": []
}}"""


def open_recognition_prompt(
    text: str,
    page_views: list[dict[str, object]],
    page_number: int,
) -> str:
    return f"""请先不依赖知识库和图纸中的bom表，直接识别电气图纸页面中的所有元器件图标。
当前识别页：第{page_number}页
待识别图片元数据：{json.dumps(page_views, ensure_ascii=False)}

当前请求只包含一张图片。bounds_in_page 表示该图片在原始页面 0 到 1000 归一化坐标中的范围。

图纸文本层：
{text[:30000]}

要求：
1. **开放识别**：忽略图纸中bom表的内容，依托大模型的图标识别和分割能力来识别部件。
2. **识别范围**：只输出实际出现的电气元器件图标（如继电器线圈、接触器、开关、指示灯、熔断器、PLC端子等）。不要把文字说明、表格边框、图框、标题栏当作元器件。
3. **系统化扫描（防漏识别）**：把页面按从左到右、从上到下划分为网格，逐格仔细扫描，不要只看显眼的大图标。**尺寸很小、线条很细、颜色很浅、被邻近线路遮挡或部分重叠的图标同样必须识别**，这些是最容易被遗漏的部件。
4. **元件名称 (name)**：填写标准的元件名称（如“中间继电器线圈”、“转换开关”、“指示灯”）。如果只能确定图标存在但不能确定具体名称，使用“未知元件名”。
5. **代号 (codes)**：提取该元件在图中的邻近代号（如 K1, SA1, FU1）。
   - 若同一类元件有多个不同代号（例如 KC1 和 KC2 都是中间继电器），请将所有代号放入一个列表中，如 ["KC1", "KC2"]。
   - 若同类元件代号相同（例如两个 SA1），列表中只保留一个代号，如 ["SA1"]，数量需要与实例数量一致。
6. **数量 (count)**：统计该类元件在图中出现的总次数。
7. **坐标 (regions)**：列出该类所有实例的 [x0,y0,x1,y1] 边界框（归一化到 0-1000）。
8. **去重**：只有完全重合的同一物理实例才合并为一次；位置不同的两个图标即使外形相同，也必须作为不同实例分别保留，不要因为相似就误删相邻图标。
9. **召回优先**：宁可多报也不要漏报。对不完全确定的图标，仍然输出，并将 confidence 设为较低值（如 0.3–0.5），在 evidence 中注明“疑似/不确定”；不要因为没有十足把握就直接丢弃。
10. **截断**：单次最多返回 100 类元件；确实超过时才将 truncated 设为 true，并且优先保留小尺寸、稀有或易遗漏的图标，不要先丢弃它们。

严格输出 JSON：
{{
  "detected_symbols": [
    {{
      "raw_label": "原始识别名称",
      "code": "图纸代号或空字符串",
      "component_type": "粗分类",
      "page": {page_number},
      "source_image_index": 1,
      "occurrence_count": 1,
      "confidence": 0.0,
      "regions": [[0, 0, 1000, 1000]],
      "evidence": "邻近文字或视觉证据"
    }}
  ],
  "truncated": false,
  "warnings": []
}}"""


def correction_prompt(
    symbol: dict[str, object],
    candidates: list[ComponentSample],
) -> str:
    candidate_metadata = [
        {
            "id": sample.id,
            "label": sample.label,
            "component_type": sample.component_type,
            "model": sample.model,
            "definition": sample.definition,
            "standards": sample.standards,
            "aliases": sample.aliases,
        }
        for sample in candidates
    ]
    return f"""根据知识库候选项，修正图纸元件的原始识别名称。
待修正元件：
{json.dumps(symbol, ensure_ascii=False)}

知识库候选：
{json.dumps(candidate_metadata, ensure_ascii=False)}

要求：
1. 只允许从候选 id 中选择 reference_id；如果都不匹配，reference_id 为空字符串。
2. label 输出规范名称，优先使用知识库 label；没有可靠匹配时保留 raw_label。
3. 结合 raw_label、code、component_type、evidence 和候选别名判断。
4. confidence 为 0 到 1；低于 0.45 时应将 reference_id 置空。
5. 不要新增候选之外的 reference_id。

严格输出 JSON：
{{
  "reference_id": "知识库id或空字符串",
  "label": "修正后的名称",
  "component_type": "修正后的类别",
  "confidence": 0.0,
  "reason": "简短依据"
}}"""


def batch_correction_prompt(
    items: list[
        tuple[dict[str, object], list[ComponentSample]]
    ],
) -> str:
    payload = [
        {
            "index": index,
            "symbol": symbol,
            "candidates": [
                {
                    "id": sample.id,
                    "label": sample.label,
                    "component_type": sample.component_type,
                    "model": sample.model,
                    "definition": sample.definition,
                    "standards": sample.standards,
                    "aliases": sample.aliases,
                }
                for sample in candidates
            ],
        }
        for index, (symbol, candidates) in enumerate(items)
    ]
    return f"""批量修正电气图纸中已经聚合完成的开放识别类别名称。
每个项目代表一种开放识别类别，occurrence_count 是该类别的实例总数，
code/codes 是这些实例的代号集合。只需修正类别名称一次，不要逐实例处理。

待修正类别：
{json.dumps(payload, ensure_ascii=False)}

要求：
1. 每个输入类别 index 必须返回一条 correction，并保持 index 不变。
2. reference_id 只能从对应项目的 candidates 中选择；均不匹配时为空字符串。
3. label 优先使用匹配知识库项的规范名称；无可靠匹配时保留 raw_label。
4. confidence 为 0 到 1；低于 0.45 时 reference_id 必须为空。
5. 不得跨项目使用候选，也不得新增候选之外的 reference_id。
6. occurrence_count 和实例坐标已经由系统确定，不需要重新识别或修改数量。
7. 如果候选是用户自定义“图形标识”，且 raw_label、code 或 evidence 明确命中其 label/aliases，
   应优先选该候选，不要因开放识别的粗分类误写成端子、断路器等通用标准符号。
8. code 的字母前缀通常指示元件类别（如 FU=熔断器，K/KC/KA=继电器，S/SA=开关，
   X/XT=端子，R=电阻或指示灯，G=电感/电源，C=电容，M=电机）。当开放识别给出的
   raw_label 或粗分类与 code 前缀指示的类别冲突时，应以 code 和 evidence 为准，
   不要被可能误标的粗 label 带偏（例如 code 为 G1/G2 时不应判为端子）。

严格输出 JSON：
{{
  "corrections": [
    {{
      "index": 0,
      "reference_id": "知识库id或空字符串",
      "label": "修正后的名称",
      "component_type": "修正后的类别",
      "confidence": 0.0,
      "reason": "简短依据"
    }}
  ]
}}"""
