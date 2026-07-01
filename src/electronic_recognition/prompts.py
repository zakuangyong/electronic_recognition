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
    return f"""直接识别当前电气图纸页面中的所有元器件符号，不依赖知识库或BOM表。

当前识别页：第{page_number}页
待识别图片元数据：{json.dumps(page_views, ensure_ascii=False)}
当前请求只包含一张图片；bounds_in_page 表示该图片在原始页面 0-1000 归一化坐标中的范围。

图纸文本层：
{text[:30000]}

识别要求：
1. 按从左到右、从上到下逐区扫描，优先保证不漏检；小尺寸、细线、浅色、被线路遮挡或局部重叠的符号也要识别。
2. 只统计图中实际出现的元器件符号；不要把BOM表、公司logo、图框、标题栏、纯文字说明、导线、线号、功能描述当作元器件。
3. 每条 detected_symbols 表示一种“同代号+同符号类型”的汇总；同一代号在不同位置重复出现时合并为一条并累计数量，不同代号通常分开输出。
4. raw_label 填中文名称，如“熔断器”“转换开关触点”“中间继电器线圈”“指示灯”“接线端子”；没把握时可自拟简短名称，并在 evidence 中说明“疑似/不确定”。
5. code 填邻近代号，如 SA1、FU、KC1、X01；没有可识别代号时填空字符串。
6. occurrence_count 必须等于 regions 的数量；regions 列出该汇总类每个实例的 [x0,y0,x1,y1] 边界框，坐标归一化到 0-1000。
7. 位置不同的相似符号都要计数；只有同一物理实例被重复框选时才去重。
8. 对不完全确定但像元器件的符号仍然输出，confidence 设为 0.3-0.5；可靠识别可设为 0.6-1.0。
9. 单次最多返回 100 类元件；确实超过时才将 truncated 设为 true，并优先保留小尺寸、稀有或易漏检的符号。

定位标准：
1. regions 使用当前输入图片自身的 0-1000 坐标系，左上角为 [0,0]，右下角为 [1000,1000]。
2. 每个框只包围元器件符号本体，排除代号文字、线号、中文说明、长导线、图框、表格和标题栏。
3. 可包含属于符号本体的触点短线、端子圆点、线圈、灯泡圆圈、熔断体等短笔画；不要把外部连接导线一起框入。
4. 框应贴近符号外轮廓，只留少量余量，避免覆盖相邻符号或文字。
5. 线圈、触点、端子、指示灯等不同符号类型不要合并成一个大框；组合组件可在 evidence 中说明其从属关系。
    
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
2. reference_id 只能从对应项目的 candidates 中选择；不得跨项目使用候选，
   也不得新增候选之外的 reference_id。
3. 匹配必须同时满足“元件大类”和“功能类型”两个维度，只有两者都吻合的候选
   才能作为 reference_id：
   - 元件大类主要看 code 字母前缀：FU/F=熔断器（F 也可能是热继电器，结合证据），
     K/KC/KA=继电器，KM=接触器，KT=时间继电器，S/SA/SF/SS=开关或按钮，
     Q/QF=断路器，X/XT 及“字母:数字”端子编号=接线端子，T/TA/CT=互感器，
     R=电阻或指示灯，G=电感/电源/信号，C=电容，M=电机。
   - 功能类型看 raw_label 与 evidence：线圈、触点（动合/动断/转换/辅助）、
     端子、开关本体、指示灯、熔断体 等。
4. 不得跨大类强行匹配：当最贴近的候选与 code 前缀或功能类型属于不同大类时
   （例如开关 SA 配成“负荷开关”、断路器 QF 配成“熔断器”、互感器 TA 配成“继电器线圈”、
   把“触点”配成“线圈”），reference_id 必须置空并保留 raw_label，不要因外形相近而误绑。
5. 在同一大类、功能一致的前提下应尽量采用知识库规范名：即使库中候选比 raw_label
   更通用（例如“继电器辅助触点”在库中只有通用的“动合触点；常开”“动断触点”），
   也应选中该候选并采用其规范 label，不要因为“不够具体”而保留原名。
6. 当同一功能存在多个更细分的候选、而证据无法区分具体子型时（例如多种“转换触点”），
   选择其中最通用或最贴合的一条，不要因无法精确到子型就整体放弃匹配。
7. confidence 为 0 到 1，应反映“元件大类+功能类型”双维度的吻合程度；
   两维度都吻合时通常≥0.6，低于 0.45 时 reference_id 必须为空。
8. label 优先使用所选候选的规范名称；reference_id 为空时保留 raw_label。
9. 如果候选是用户自定义“图形标识”，且 raw_label、code 或 evidence 明确命中其 label/aliases，
   应优先选该候选，不要因开放识别的粗分类误写成端子、断路器等通用标准符号。
10. occurrence_count 和实例坐标已经由系统确定，不需要重新识别或修改数量。

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
