# 版面/功能区域路由层改造计划

## 1. 背景与目标

当前识别流程在 `RecognitionPipeline` 中将每一页图纸渲染为整页图片，再通过固定网格生成切片，并对所有切片调用视觉模型。该方式实现简单，但存在三个明显问题：

1. 标题栏、元件表、图框、空白区等区域仍会进入元件开放识别，产生无效模型调用。
2. 标题栏和元件表目前主要依赖 PDF 文字层；扫描 PDF、文字层损坏或非标准版式时稳定性不足。
3. 固定网格可能截断跨切片元件，且无法根据图纸内容密度动态调整识别范围。

本次改造在文档解析与各类下游识别器之间增加“版面/功能区域路由层”，将每页划分为可解释的功能区域，并根据区域类型选择不同处理路径。

目标如下：

1. 减少标题栏、元件表、空白区等非电气符号区域的视觉模型调用。
2. 提高标题栏、元件表在扫描件和无文字层 PDF 中的提取成功率。
3. 降低固定切片造成的元件截断和重复识别。
4. 为后续页面级检索、功能块检索和连线拓扑识别提供统一区域数据。
5. 保持现有 `/analyze` API 和 `RecognitionResult` 主要字段向后兼容。

首期不包含：

- 电气连线、网络拓扑和回路图重建。
- 面向所有工程图纸类型的通用版面检测。
- 对历史识别结果进行自动覆盖或静默重算。
- 将区域检测模型作为识别服务不可替代的强依赖。

## 2. 成功指标

应先建立固定评测集，以当前代码作为基线。建议选取至少 50 份图纸，覆盖：

- 含 PDF 文字层的标准图纸。
- 无文字层的扫描 PDF。
- 单页和多页图纸。
- 标题栏位于不同位置的图纸。
- 含元件表、端子表、修订栏和大面积空白的图纸。
- 高密度控制回路和低密度说明页。

首期验收指标：

| 指标 | 目标 |
|---|---:|
| 无效视觉模型调用数 | 相对基线降低至少 40% |
| 单页平均模型请求数 | 相对基线降低至少 30% |
| 端到端平均耗时 | 相对基线降低至少 25% |
| 标题栏关键字段完整率 | 相对基线提高至少 15% |
| 扫描件元件表可用提取率 | 达到 70% 以上 |
| 元件实例召回率 | 相对基线下降不超过 2 个百分点 |
| 重复元件框数量 | 相对基线降低至少 20% |
| 区域路由失败时可回退率 | 100% |

“无效视觉模型调用”定义为：模型返回零个元件，且对应区域经人工检查仅包含空白、图框、标题栏、表格或说明文字。

## 3. 现状与改造入口

### 3.1 当前主要流程

当前流程：

```text
PDF / PNG
  -> parse_document() 渲染页面并提取 PDF 文字
  -> PDF 标题栏规则提取
  -> PDF 控制信号规则提取
  -> PDF 元件表规则提取
  -> _build_page_views() 生成整页图和固定网格切片
  -> 逐切片开放视觉识别
  -> RAG 名称修正
  -> 元件合并去重
  -> 组合规则判断
  -> result.json 和步骤文件
```

关键代码入口：

- `src/electronic_recognition/document.py`
  - `parse_document()`
- `src/electronic_recognition/pipeline.py`
  - `RecognitionPipeline.analyze()`
  - `_analyze_vision_first()`
  - `_analyze_rag_first()`
  - `_build_page_views()`
- `src/electronic_recognition/title_block_extractor.py`
  - `extract_title_block()`
- `src/electronic_recognition/component_table_extractor.py`
  - `extract_component_table()`
- `src/electronic_recognition/api.py`
  - 进度步骤文件和识别结果持久化

### 3.2 当前问题在代码中的表现

1. `_build_page_views()` 只根据固定 `tile_grid` 和 `tile_overlap` 生成切片，不理解内容。
2. `_analyze_vision_first()` 默认把每个切片都发送给开放识别模型。
3. 标题栏提取只在 PDF 第一页使用文字层规则，OCR 后端未在主流程中配置。
4. 元件表提取只处理 PDF 文字层，扫描 PDF 返回空结果。
5. 页面类型没有结构化表示，下游无法区分主回路、控制回路、表格或说明页。

## 4. 总体架构

改造后流程：

```text
PDF / PNG
  -> 页面渲染、文字层和页面质量分析
  -> 版面/功能区域路由
       ├─ title_block       -> 标题栏文字层解析 / 区域 OCR / VLM 提取
       ├─ component_table   -> 表格文字层解析 / 区域 OCR / VLM 提取
       ├─ terminal_table    -> 端子表专用提取或结构化保留
       ├─ revision_block    -> 修订信息提取
       ├─ main_circuit      -> 元件视觉识别
       ├─ control_circuit   -> 元件视觉识别
       ├─ circuit_unknown   -> 元件视觉识别
       ├─ notes             -> 文字提取，不进入元件识别
       ├─ frame_or_margin   -> 跳过
       └─ blank             -> 跳过
  -> 区域结果合并到页面坐标
  -> RAG 名称修正
  -> 元件合并去重
  -> 组合规则判断
  -> 结果和区域步骤持久化
```

路由层采用渐进式实现：

1. 规则和图像启发式优先，避免首期必须训练模型。
2. 可选轻量检测模型补充非标准版式。
3. 低置信度或路由异常时回退到现有固定网格流程。

## 5. 区域模型设计

### 5.1 数据结构

在 `models.py` 中增加以下结构，或在独立的 `layout_models.py` 中定义：

```python
@dataclass(slots=True)
class LayoutRegion:
    id: str
    page: int
    region_type: str
    bounds: list[float]          # 页面 0-1000 归一化坐标
    confidence: float
    source: str                 # pdf_text / heuristic / detector / fallback
    route: str                  # component / structured / text / skip
    hints: dict[str, Any]


@dataclass(slots=True)
class PageLayout:
    page: int
    width: int
    height: int
    scan_likelihood: float
    text_coverage: float
    regions: list[LayoutRegion]
    fallback_required: bool = False
```

区域类型首期固定为：

```text
title_block
component_table
terminal_table
revision_block
main_circuit
control_circuit
circuit_unknown
notes
frame_or_margin
blank
```

路由动作固定为：

```text
component   元件识别
structured  标题栏、表格等结构化提取
text        只做文字提取
skip        不进入模型
```

### 5.2 坐标约定

- 对外统一使用页面左上角原点、`0-1000` 的归一化坐标。
- 内部图像裁剪时转换为像素坐标。
- PDF 文字块使用 PDF 页面坐标，进入路由结果前转换为统一坐标。
- 所有区域必须保留来源、置信度和原始推断依据，方便调试。

### 5.3 区域重叠规则

1. `title_block`、`component_table`、`terminal_table` 和 `revision_block` 优先于通用电气区域。
2. 电气区域与结构化区域重叠部分应从电气识别裁剪范围中扣除。
3. 相邻且类型相同的电气区域可以合并，但必须设置最大面积和最大宽高比。
4. 检测器产生的多个高度重叠区域通过 NMS 或包含关系合并。
5. 距离图像边缘过近的狭窄区域默认标记为 `frame_or_margin`，但不能覆盖真实元件区域。

## 6. 页面质量与扫描件判断

新增 `PageQualityAnalyzer`，输出：

- PDF 文字字符数。
- 文字覆盖率。
- 图像边缘密度。
- 长直线密度。
- 白色像素占比。
- 图像清晰度。
- 倾斜角度估计。
- `scan_likelihood`。

扫描件判断不要求一次做到完美，首期可使用下列组合：

```text
PDF 文字字符数很少
+ 页面包含大面积连续位图
+ 边缘/线条密度符合图纸特征
= 高扫描概率
```

处理策略：

- 文字层可靠：优先文字层规则提取。
- 文字层不完整：对推断出的结构化区域做 OCR。
- 无文字层扫描件：先做区域路由，再对标题栏、表格和说明区分别 OCR。
- 页面倾斜明显：OCR 前对区域图像做旋转校正，原始页面坐标保持不变。

## 7. 区域路由实现策略

### 7.1 第一阶段：规则与启发式路由

第一阶段不训练模型，复用已有提取器已经推断出的区域：

1. `extract_title_block()` 返回的 `region` 作为标题栏候选。
2. `extract_component_table()` 各页面返回的 `region` 作为元件表候选。
3. 根据文字关键词识别端子表、修订栏和说明区。
4. 检测大面积空白、图框和页边坐标区。
5. 从页面剩余区域中生成电气识别区域。

建议规则：

- 标题栏：现有字段标签、公司名称和页码模式共同定位。
- 元件表：现有表头列名和序号连续性定位。
- 端子表：包含“端子、端子号、线号、接线”等关键词，并呈现高密度表格线。
- 修订栏：包含“版本、修改、日期、签字、REV”等关键词。
- 说明区：连续文字密度高但标准电气符号密度低。
- 空白区：前景像素占比低于阈值。
- 电气区：扣除上述区域后，按前景连通性和线条密度生成包围区域。

第一阶段仍允许电气区内部继续细分，但切片由内容边界决定，不再固定覆盖整页。

### 7.2 第二阶段：轻量区域检测器

当规则路由在评测集上达到稳定基线后，引入可选检测器。

建议标注类型：

- `title_block`
- `component_table`
- `terminal_table`
- `revision_block`
- `main_circuit`
- `control_circuit`
- `notes`

标注建议：

- 第一批 150-300 页，优先选择项目实际图纸。
- 训练/验证/测试按图纸文件划分，避免同一文件不同页泄漏。
- 保留不同项目、公司模板和扫描质量的分布。
- 使用规则结果预标注，人工校正以降低标注成本。

模型接口应抽象为：

```python
class LayoutDetector(Protocol):
    def detect(self, image_path: Path, page: int) -> list[LayoutRegion]:
        ...
```

具体模型实现可以是 YOLO 小模型，但主流程不得直接依赖特定框架。无模型文件、推理失败或置信度不足时自动使用规则路由。

### 7.3 第三阶段：规则与模型融合

融合优先级：

1. 高置信度文字层结构化区域。
2. 高置信度检测器区域。
3. 图像启发式区域。
4. 固定网格回退区域。

结构化区域可以由多来源交叉增强：

- 文字层找到标题栏标签，但范围不完整时，检测器负责扩展边界。
- 检测器找到表格，但无文字层时，区域 OCR 负责内容提取。
- 检测器与文字层冲突时保留两者证据，并使用置信度和模板规则决策。

## 8. 区域内处理策略

### 8.1 标题栏

处理顺序：

```text
PDF 文字层规则
  -> 缺字段时对标题栏区域 OCR
  -> OCR 仍缺字段时调用短 Prompt 的 VLM 结构化提取
  -> 字段规范化与 schema 校验
```

关键字段：

- 客户名称
- 工程名称
- 系统名称
- 公司名称
- 合同号
- 版本号
- 图纸名称
- 原理图号
- 当前页
- 总页数

VLM 只接收标题栏裁剪图，不接收整页，输出必须是固定 JSON。

### 8.2 元件表

处理顺序：

```text
PDF 文字层表格规则
  -> 缺行或无结果时区域 OCR
  -> OCR 文本按列结构恢复
  -> 必要时 VLM 表格结构化
  -> 行级校验、代号规范化、去重
```

表格输出继续保持：

- 序号
- 代号
- 元件名称
- 规格型号
- 数量
- 备注
- 页码

### 8.3 电气功能区域

只把以下区域送入元件视觉识别：

- `main_circuit`
- `control_circuit`
- `circuit_unknown`

识别图像列表由区域路由层生成，替代 `_build_page_views()` 的固定整页覆盖。每个视图应带：

```json
{
  "path": "...",
  "kind": "layout_region",
  "region_id": "page-1-control-1",
  "region_type": "control_circuit",
  "bounds": [100, 120, 780, 860],
  "confidence": 0.91
}
```

如果区域面积过大，允许区域内部按密度自适应切分，并保留重叠。

### 8.4 跳过区域

以下区域默认不调用元件识别模型：

- 标题栏
- 元件表
- 修订栏
- 说明文字
- 图框和页边
- 空白区

在调试模式下可以保存跳过区域截图和原因，但生产模式不必长期保存全部截图。

## 9. 主流程改造

### 9.1 新增模块

建议新增：

```text
src/electronic_recognition/
  layout_models.py
  layout_router.py
  layout_detector.py
  page_quality.py
  region_images.py
  ocr.py
  structured_region_extractor.py
```

职责：

- `layout_models.py`：区域和页面版面数据结构。
- `layout_router.py`：规则路由、模型融合和回退。
- `layout_detector.py`：检测器协议与可选实现。
- `page_quality.py`：扫描概率、空白、清晰度等分析。
- `region_images.py`：裁剪、去倾斜和坐标转换。
- `ocr.py`：OCR 后端协议和实现。
- `structured_region_extractor.py`：标题栏、元件表和修订栏的多级回退编排。

### 9.2 `document.py`

扩展 `ParsedPage`，增加可选字段：

```python
width: int
height: int
text_length: int
has_text_layer: bool
```

保持原字段可用，避免破坏测试和已有调用。

### 9.3 `pipeline.py`

在文档解析后增加：

```python
page_layouts = self.layout_router.route(document, directory)
```

再将标题栏、元件表和视觉识别改为消费 `page_layouts`。

需要重构：

- `_analyze_vision_first()`：接收路由后的电气区域视图。
- `_analyze_rag_first()`：同样使用路由后的视图，避免两种模式行为不一致。
- `_build_page_views()`：保留为回退函数，新建 `_build_routed_page_views()`。
- `_remap_component_regions()`：继续使用视图 `bounds`，无需改变外部坐标格式。

### 9.4 `models.py`

`RecognitionResult` 增加可选字段：

```python
page_layouts: list[dict[str, Any]] = field(default_factory=list)
```

如果不希望扩大主结果文件，也可只在 `recognition_steps` 中保存摘要。推荐主结果保留区域摘要，详细区域放步骤文件。

### 9.5 `api.py`

新增步骤文件：

```text
steps/01-page-quality.json
steps/02-layout-regions.json
steps/03-structured-regions.json
```

现有步骤编号可能已被前端使用，因此实施时优先使用新的稳定名称，不强制重排旧文件名。

进度事件：

```text
page_quality
layout_regions
structured_region_extraction
layout_fallback
```

## 10. 配置设计

在 `Settings` 中增加：

```text
ER_LAYOUT_ROUTING_ENABLED=true
ER_LAYOUT_ROUTER_MODE=hybrid
ER_LAYOUT_MODEL_PATH=
ER_LAYOUT_MIN_CONFIDENCE=0.45
ER_LAYOUT_FALLBACK_TO_GRID=true
ER_LAYOUT_SAVE_REGION_IMAGES=false
ER_SCAN_TEXT_THRESHOLD=40
ER_REGION_OCR_ENABLED=true
ER_REGION_VLM_FALLBACK_ENABLED=true
ER_REGION_MAX_AREA_RATIO=0.65
ER_REGION_TILE_OVERLAP=0.12
```

`ER_LAYOUT_ROUTER_MODE`：

- `rules`：只使用文字层和启发式。
- `detector`：优先检测器，失败时按配置回退。
- `hybrid`：规则与检测器融合。
- `disabled`：完全使用现有固定网格流程。

默认上线策略应为：

```text
ER_LAYOUT_ROUTING_ENABLED=true
ER_LAYOUT_ROUTER_MODE=rules
ER_LAYOUT_FALLBACK_TO_GRID=true
```

检测器经过评测后再将默认模式调整为 `hybrid`。

## 11. 扫描件 OCR 接入

### 11.1 OCR 抽象

定义统一协议：

```python
class OCRBackend(Protocol):
    def recognize(
        self,
        image_path: Path,
        *,
        language: str = "zh-en",
    ) -> OCRResult:
        ...
```

`OCRResult` 至少包含：

- 文本。
- 文字框。
- 每个文字框置信度。
- 引擎名称。
- 耗时。

### 11.2 部署策略

OCR 应为可选依赖，不影响只处理带文字层 PDF 的轻量部署。建议在 `pyproject.toml` 增加可选依赖组：

```toml
[project.optional-dependencies]
ocr = [...]
layout = [...]
```

OCR 引擎不可用时：

- 保留标题栏和表格空结果。
- 写入明确 warning。
- 不得导致整份识别任务失败。

### 11.3 预处理

区域 OCR 前可执行：

- 灰度化。
- 自适应二值化。
- 对比度增强。
- 轻度去噪。
- 倾斜校正。
- 2-3 倍放大。

每个预处理步骤应可配置，并保存原始区域与处理后区域的哈希，便于缓存。

## 12. 缓存与性能

缓存键建议由以下内容组成：

```text
source_file_hash
+ page_number
+ region_bounds
+ region_type
+ router_version
+ preprocessing_version
+ OCR/model配置
```

缓存内容：

- 页面质量分析。
- 区域路由结果。
- 区域裁剪图。
- OCR 结果。
- VLM 结构化结果。

缓存失效条件：

- 原文件变化。
- 路由器版本变化。
- 区域检测模型变化。
- OCR 预处理配置变化。

## 13. 测试计划

### 13.1 单元测试

新增：

```text
tests/test_page_quality.py
tests/test_layout_router.py
tests/test_region_images.py
tests/test_structured_region_extractor.py
tests/test_layout_pipeline.py
```

覆盖：

- PDF 坐标到归一化坐标转换。
- 区域裁剪和元件框坐标回映射。
- 区域重叠、合并和扣除。
- 标题栏/元件表区域优先级。
- 空白区跳过。
- 低置信度回退到固定网格。
- OCR 后端失败时不中断任务。
- 路由结果缓存命中与失效。

### 13.2 集成测试

至少准备：

- 标准文字层 PDF。
- 扫描 PDF。
- PNG 图纸。
- 标题栏位置不同的图纸。
- 只有表格、没有电气回路的页面。
- 电气回路占满整页的页面。

验证：

- `result.json` 原有字段仍存在。
- 电气区域中的元件框能正确回映射到整页。
- 标题栏和元件表不会再次作为元件送入视觉模型。
- 路由失败时结果与旧流程一致。

### 13.3 回归评测脚本

新增：

```text
scripts/evaluate_layout_routing.py
```

输出：

- 每份图纸的区域数量。
- 模型请求数量。
- 空结果调用数量。
- 总耗时。
- 元件数量和人工标注召回率。
- 标题栏字段完整率。
- 表格行准确率。
- 路由回退次数。

保存基线和新版本两份 JSON，生成对比报告。

## 14. 分阶段实施

### 阶段 0：基线与评测集

任务：

1. 固定 50 份评测图纸。
2. 保存当前识别结果和模型请求统计。
3. 人工标注标题栏、表格、电气区域和主要元件实例。
4. 建立评测脚本。

交付：

- 基线数据集清单。
- 基线结果 JSON。
- 指标报告。

### 阶段 1：规则路由与无效区域排除

任务：

1. 增加页面质量分析。
2. 复用现有标题栏和元件表区域。
3. 增加空白、图框、说明区识别。
4. 从剩余区域生成电气识别视图。
5. 接入回退机制和步骤文件。

验收重点：

- 模型请求减少。
- 元件召回基本不下降。
- 可通过配置完全回退旧流程。

### 阶段 2：扫描件区域 OCR

任务：

1. 接入 OCR 协议。
2. 标题栏区域 OCR 回退。
3. 元件表区域 OCR 与结构恢复。
4. 页面倾斜和图像增强。
5. 增加 OCR 缓存。

验收重点：

- 无文字层扫描件可获得标题栏和元件表结果。
- OCR 失败不影响元件识别。

### 阶段 3：轻量区域检测器

任务：

1. 建立标注集和数据版本。
2. 训练并评估检测模型。
3. 实现 `LayoutDetector`。
4. 增加规则与模型融合。
5. 对非标准版式进行专项测试。

验收重点：

- 非标准版式区域召回提高。
- 检测器故障可自动回退。

### 阶段 4：区域感知的组合判断

任务：

1. 将 `region_id` 和 `region_type` 传递到元件记录。
2. 组合规则增加同区域、邻近区域等可选约束。
3. 不改变现有规则的默认行为。

该阶段不是首期上线阻塞项。

## 15. 风险与控制

### 15.1 电气区域漏检

风险：路由层漏掉电气区域会直接降低元件召回。

控制：

- 低置信度页面默认回退固定网格。
- 对未被结构化区域覆盖但前景密度较高的区域统一生成 `circuit_unknown`。
- 首期只排除高置信度非电气区域。

### 15.2 结构化区域边界不准

风险：标题栏或表格区域过大，吞掉真实电气回路。

控制：

- 使用文字框和线条共同约束边界。
- 设置结构化区域最大面积比例。
- 对区域边界保留小幅安全间距，但不能无限扩张。

### 15.3 OCR 增加资源占用

风险：本地 OCR 模型增加内存、安装和冷启动成本。

控制：

- OCR 作为可选依赖。
- 仅对缺字段的结构化区域调用。
- 使用缓存。
- 限制并发。

### 15.4 检测模型域偏移

风险：不同项目图框模板导致检测失效。

控制：

- 训练集按项目和模板分层。
- 保留规则路由。
- 线上记录低置信度区域，进入后续标注闭环。

## 16. 可观测性

在 `meta` 中增加：

```json
{
  "layout_router_mode": "rules",
  "layout_region_count": 8,
  "component_region_count": 3,
  "structured_region_count": 2,
  "skipped_region_count": 3,
  "layout_fallback_page_count": 0,
  "scan_page_count": 1,
  "ocr_request_count": 2,
  "structured_vlm_request_count": 0,
  "avoided_component_model_requests": 5
}
```

日志应能回答：

- 哪个页面被判定为扫描件。
- 哪些区域被跳过以及原因。
- 哪些区域进入元件识别。
- 哪些结构化字段触发 OCR/VLM 回退。
- 哪些页面使用固定网格回退。

## 17. 发布与回滚

发布步骤：

1. 规则路由以配置开关方式合入。
2. 在测试环境对历史结果批量重放。
3. 对比基线指标并人工抽检。
4. 生产默认开启规则路由和固定网格回退。
5. 检测器成熟后再启用 `hybrid` 模式。

回滚：

- 设置 `ER_LAYOUT_ROUTING_ENABLED=false`。
- 不删除原 `_build_page_views()`。
- 新字段均为可选字段。
- 新步骤文件不改变旧步骤文件读取。

## 18. 完成定义

满足以下条件视为首期完成：

1. 识别主流程已接入规则版区域路由。
2. 标题栏、元件表和空白区不会进入元件开放识别。
3. 扫描件结构化区域具备 OCR 回退。
4. 每页路由结果、来源、置信度和回退状态可追踪。
5. 固定评测集的元件召回下降不超过 2 个百分点。
6. 无效模型调用降低至少 40%。
7. 所有现有测试通过，新增区域路由测试通过。
8. 可以通过一个环境变量完整回退到旧流程。

