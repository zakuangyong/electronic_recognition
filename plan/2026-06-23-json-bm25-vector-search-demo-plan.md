# 基于现有 JSON 结果的 BM25＋向量混合检索 Demo 实施计划

## 1. 目标与范围

本计划基于当前 `result/{result_id}/result.json` 及 `steps/*.json` 构建一个可演示、可重复重建的图纸检索 Demo。

Demo 目标：

1. 不重新执行图纸识别，直接消费已有 JSON 结果。
2. 保留现有 Exact＋SQLite FTS5 BM25 检索。
3. 增加真实文本 Embedding 和本地 Qdrant 向量检索。
4. 使用 RRF 融合 Exact、BM25 和 Dense 三路结果。
5. 搜索结果按图纸聚合，并说明命中页面、元件、组合规则和召回来源。
6. Qdrant 或 Embedding 不可用时自动降级为 Exact＋BM25。
7. 通过一组固定查询直观展示 BM25 与混合检索的差异。

本阶段不包含：

- 图像向量检索。
- OCR 或识别模型重跑。
- 大模型重排。
- 分布式 Qdrant 集群。
- 面向万级图纸的正式性能验收。
- 自动更新历史识别结果中的元件或规则判断。

## 2. 当前基础

项目已经具备：

- `DrawingDocumentBuilder`：从识别结果生成图纸和子文档。
- `DrawingSearchStore`：SQLite 元数据、精确字段和 FTS5 BM25 索引。
- `DrawingSearchService`：Exact、BM25、RRF 和图纸聚合框架。
- `/api/search`、`/api/search/health`、索引重建接口。
- `/search` 检索演示页面。
- `data/search/drawings.db`，当前已有历史结果索引。
- `result/` 下 16 份可用识别结果。

当前主要缺口：

- `dense_hits` 仍为空列表。
- 没有 Embedding 后端实现。
- 没有 Qdrant collection 初始化、写入、删除和查询实现。
- 索引流程只写 SQLite，没有写入向量库。
- 健康检查固定报告 Qdrant 和 Embedding 不可用。
- 历次识别中存在同一源图纸的重复结果，需要在展示层去重或折叠。

## 3. JSON 数据来源与优先级

每个结果目录按以下优先级读取：

### 3.1 权威汇总数据

优先读取：

```text
result/{result_id}/result.json
```

使用字段：

- `document`
- `title_block`
- `control_signal_configuration`
- `component_table`
- `page_layouts`
- `detected_components`
- `detected_combinations`
- `preview_pages`
- `meta`
- `warnings`

### 3.2 步骤文件补充

当 `result.json` 缺少字段或需要更详细语义时读取：

```text
steps/01-title-block.json
steps/02-control-signal-configuration.json
steps/03-component-table.json
steps/04-open-symbols.json
steps/05-rag-corrections.json
steps/06-detected-components.json
steps/06-detected-combinations.json
steps/09-meta.json
```

约定：

1. 最终元件优先使用 `steps/06-detected-components.json`；不存在时使用 `result.json.detected_components`。
2. 最终组合优先使用 `steps/06-detected-combinations.json`；不存在时使用 `result.json.detected_combinations`。
3. `05-rag-corrections.json` 只用于补充修正原因、原始名称和候选语义，不直接作为最终元件事实。
4. `04-open-symbols.json` 只作为开放识别证据，不覆盖最终元件。
5. 索引必须记录实际读取过的文件及其哈希，便于判断是否需要重建。

## 4. Demo 技术选型

### 4.1 关键词检索

继续使用现有：

```text
SQLite FTS5 BM25
```

不替换现有数据库和查询接口。

### 4.2 Embedding

Demo 默认采用本地中文模型：

```text
BAAI/bge-small-zh-v1.5
```

原因：

- CPU 环境比 BGE-M3 更容易启动。
- 当前数据量小，足以验证中文电气语义检索。
- 后端接口保持通用，后续可切换到 `BAAI/bge-m3`。

新增可选依赖：

```toml
search = [
  "qdrant-client>=1.9",
  "sentence-transformers>=3.0"
]
```

模型必须通过配置指定，不在业务代码中写死。

### 4.3 向量存储

Demo 使用 Qdrant Local Mode：

```text
data/search/qdrant/
```

优点：

- 不要求单独启动 Docker 或 Qdrant 服务。
- 数据可以持久化，重启应用后仍可查询。
- API 与远程 Qdrant 基本一致，后续迁移成本低。

同时保留远程模式：

```text
ER_SEARCH_QDRANT_MODE=local|remote
ER_SEARCH_QDRANT_PATH=data/search/qdrant
ER_SEARCH_QDRANT_URL=http://127.0.0.1:6333
```

### 4.4 融合

继续使用现有 RRF：

```text
Exact Top-N
+ BM25 Top-50
+ Dense Top-50
-> RRF(k=60)
-> 按 drawing_id 聚合
```

首版不直接混加 BM25 原始分数和余弦相似度。

## 5. 检索文档与切块设计

不把原始 JSON 整体序列化后直接向量化。使用稳定模板生成领域文本。

### 5.1 图纸摘要块

每个结果生成一个 `drawing` 块：

```text
图纸文件：A17387_1706_项目原理图_07.pdf
工程名称：成都轨道交通18号线工程
图纸名称：组合式风阀MD
图号：CDDT-6-DZ-.07
合同号：A17387
元件：K1 交流继电器线圈；SA1 选择开关；……
组合功能：继电器线圈与辅助触点组合；……
控制方式：自动；手动；PLC输入输出
```

用途：

- 图纸级语义召回。
- 标题、工程和功能综合查询。

### 5.2 页面块

每页生成一个 `page` 块：

```text
第1页。
元件：K1 交流继电器线圈；K2 交流继电器线圈；……
组合功能：继电器线圈与辅助触点组合。
控制信号：自动、切除、手动、小PLC输入、小PLC输出。
```

用途：

- 返回命中页。
- 避免多页图纸被压缩成一个过长向量。

### 5.3 元件组块

按页面和 `component_type` 分组生成 `component_group` 块。

示例：

```text
第1页继电器及驱动器件。
K1、K2、K3、KC1、KC2，交流继电器线圈，共5个。
识别依据：控制输出回路中的矩形线圈符号。
```

用途：

- “包含多个继电器线圈的图纸”。
- “带选择开关和 PLC 端子的控制图”等元件组合查询。

### 5.4 组合规则块

每个最终组合生成一个 `combination` 块：

```text
第1页识别到继电器线圈与辅助触点组合。
规则：coil_contact_group。
层级：builtin。
组号：K1。
成员：线圈K1；辅助触点K1，共3个。
证据：线圈与触点使用相同基础代号。
```

自定义规则必须保留：

- `rule_id`
- `rule_layer`
- `name`
- `members`
- `evidence`

### 5.5 RAG 修正语义

不为每条 `05-rag-corrections` 单独建向量。只将以下字段合并到对应最终元件块：

- `raw_label`
- 最终 `label`
- `component_type`
- `correction_reason`
- `reference_id`

这样可以检索原始叫法，同时避免候选列表产生大量噪声。

## 6. 去重策略

当前 `result/` 中包含同一图纸的多次识别结果。Demo 采用“全部索引、默认折叠”的策略。

### 6.1 身份字段

保留：

- `result_id`：一次识别任务。
- `source_hash`：原输入文件内容哈希。
- `drawing_key`：规范化图号；无图号时使用规范化文件名。
- `drawing_id`：具体识别结果的稳定 ID。

### 6.2 默认展示

搜索结果默认按以下键折叠：

```text
source_hash
```

相同 `source_hash` 只显示最新一次成功识别结果。

若旧结果缺少输入文件，退化为：

```text
normalized drawing_number + normalized filename
```

调试模式允许显示全部历史识别版本。

### 6.3 索引原则

Demo 首次实现可先全部写入 SQLite/Qdrant，查询聚合阶段再折叠。这样不会丢失历史数据，也方便比较不同识别版本。

## 7. 新增模块

在 `src/electronic_recognition/search/` 新增：

```text
embedding.py
qdrant_store.py
json_result_loader.py
```

### 7.1 `json_result_loader.py`

职责：

- 读取 `result.json`。
- 按优先级补充 `steps` 中的最终元件和最终组合。
- 兼容旧结果目录缺少步骤文件的情况。
- 输出统一 payload 给 `DrawingDocumentBuilder`。
- 记录输入文件列表及内容哈希。

建议接口：

```python
class JsonResultLoader:
    def load(self, result_dir: Path) -> LoadedRecognitionResult:
        ...
```

### 7.2 `embedding.py`

定义：

```python
class EmbeddingBackend(Protocol):
    @property
    def model_id(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed_documents(
        self, texts: list[str]
    ) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...
```

实现：

```text
SentenceTransformerEmbeddingBackend
DisabledEmbeddingBackend
```

要求：

- 延迟加载模型。
- 批量生成向量。
- 默认对向量做归一化。
- 模型加载失败给出明确错误。
- 测试中可注入 FakeEmbeddingBackend。

### 7.3 `qdrant_store.py`

职责：

- 创建并校验 collection。
- 按 `chunk_id` 生成稳定 point ID。
- upsert chunk 向量。
- 删除某个 `drawing_id` 或 `result_id` 的向量。
- 执行向量 Top-K 查询。
- 返回统一 `SearchHit(source="dense")`。
- 提供健康检查和 point 数量。

Qdrant payload 至少包含：

```json
{
  "chunk_id": "...",
  "drawing_id": "...",
  "result_id": "...",
  "chunk_type": "combination",
  "page": 1,
  "region_type": "",
  "content_hash": "...",
  "schema_version": 2,
  "builder_version": "2",
  "embedding_model": "BAAI/bge-small-zh-v1.5"
}
```

## 8. 现有模块改造

### 8.1 `document_builder.py`

改造内容：

1. `version` 升级为 `2`。
2. 使用统一 JSON loader 输出。
3. 增加 `component_group` 块。
4. 在组合块中加入 `rule_id` 和 `rule_layer`。
5. 将 RAG 修正后的 `raw_label` 和 `correction_reason` 写入元件语义文本。
6. 为每个 chunk 填充可供 Qdrant 使用的 metadata。
7. 修复中文字段别名和编码异常，确保生成文本为有效 UTF-8 中文。

### 8.2 `index_service.py`

索引流程调整为：

```text
读取 JSON
-> 构建 DrawingDocument
-> SQLite upsert
-> 批量计算 chunk embeddings
-> Qdrant upsert
-> 更新索引状态
```

接口返回增加：

```json
{
  "status": "complete",
  "chunks": 12,
  "vectors": 12,
  "embedding_model": "BAAI/bge-small-zh-v1.5"
}
```

失败策略：

- SQLite 成功、向量失败：记录 `vector_failed`，BM25 仍可用。
- `--bm25-only`：只重建 SQLite。
- `--vector-only`：读取 SQLite chunk 后补建向量。
- `--force`：忽略内容哈希，全部重建。

### 8.3 `search_service.py`

改造内容：

1. 注入 `EmbeddingBackend` 和 `QdrantVectorStore`。
2. `hybrid` 模式下生成 query embedding。
3. 调用 Qdrant 返回 `dense_hits`。
4. Exact、BM25、Dense 并行或顺序执行后进入现有 RRF。
5. `match_counts.dense` 返回真实数量。
6. `degraded` 只在向量后端异常或配置关闭时为 `true`。
7. Debug 响应增加每个结果的 BM25 rank、Dense rank、RRF score。

模式约定：

```text
disabled  检索关闭
bm25      Exact＋BM25
vector    Dense only，用于对照
hybrid    Exact＋BM25＋Dense＋RRF
```

### 8.4 `api.py`

改造：

- `_index_service()` 注入 Embedding 和 Qdrant。
- `_search_service()` 注入 Embedding 和 Qdrant。
- `/api/search/health` 返回真实状态。
- `/api/search/rebuild` 支持 `mode`：

```json
{
  "force": false,
  "mode": "all"
}
```

可选值：

```text
all
bm25
vector
```

### 8.5 `config.py`

新增：

```text
ER_SEARCH_QDRANT_MODE=local
ER_SEARCH_QDRANT_PATH=data/search/qdrant
ER_SEARCH_EMBEDDING_BACKEND=sentence_transformers
ER_SEARCH_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
ER_SEARCH_EMBEDDING_NORMALIZE=true
ER_SEARCH_MODE=hybrid
ER_SEARCH_DEDUPLICATE=true
```

生产试验 BGE-M3 时只需替换模型配置：

```text
ER_SEARCH_EMBEDDING_MODEL=BAAI/bge-m3
```

## 9. 索引状态和缓存

### 9.1 SQLite 状态

在 `drawings` 或独立状态表记录：

- `bm25_status`
- `vector_status`
- `vector_count`
- `embedding_model`
- `builder_version`
- `indexed_at`
- `vector_indexed_at`
- `last_error`

### 9.2 Embedding 缓存

新增 SQLite 表：

```sql
CREATE TABLE embedding_cache (
    cache_key TEXT PRIMARY KEY,
    model_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    dimension INTEGER NOT NULL,
    vector_blob BLOB NOT NULL,
    created_at TEXT NOT NULL
);
```

缓存键：

```text
model_id + builder_version + content_hash
```

当前仅 16 份结果，缓存不是性能必需项，但可以避免反复下载或重复计算时造成 Demo 等待。

## 10. 重建脚本

扩展现有：

```text
scripts/rebuild_drawing_search_index.py
```

支持：

```powershell
python scripts/rebuild_drawing_search_index.py --mode all --force
python scripts/rebuild_drawing_search_index.py --mode bm25
python scripts/rebuild_drawing_search_index.py --mode vector
python scripts/rebuild_drawing_search_index.py --result-id <id>
```

输出示例：

```json
{
  "scanned": 16,
  "indexed": 16,
  "skipped": 0,
  "failed": [],
  "chunks": 145,
  "vectors": 145,
  "duplicates": 9,
  "elapsed_seconds": 18.4
}
```

重建前不删除原库。全量构建到新 collection：

```text
electronic_drawing_chunks_demo_v2
```

校验成功后再切换配置，避免中途中断导致现有 BM25 Demo 不可用。

## 11. 前端 Demo 调整

复用现有 `/search` 页面，增加：

- 当前模式：BM25 / Vector / Hybrid。
- 健康状态：Embedding、Qdrant、SQLite。
- 结果标签：`精确命中`、`BM25`、`语义命中`。
- 命中 chunk 类型：图纸摘要、页面、元件组、组合规则。
- 命中页码。
- 相同源图纸的历史版本折叠提示。
- Debug 开关，用于展示三路排名。

搜索请求增加可选对照模式：

```json
{
  "query": "带继电器联动和PLC控制的风阀图纸",
  "retrieval_mode": "hybrid",
  "debug": true
}
```

`retrieval_mode` 仅用于 Demo 对比，不覆盖服务器安全配置。

## 12. Demo 查询集

建立：

```text
data/search/demo_queries.json
```

至少包含以下查询：

### 12.1 精确检索

```text
A17387
CDDT-6-DZ-.07
LCAE1-G-1
K1
SA1
```

### 12.2 关键词检索

```text
排烟风机
组合式风阀
交流继电器线圈
PLC输入输出端子
线圈辅助触点
```

### 12.3 语义检索

```text
带多个继电器联动的控制图
可以手动自动切换的风阀控制回路
包含PLC输入和输出信号的图纸
用于排烟风机控制的原理图
线圈和辅助触点属于同一设备的图纸
```

### 12.4 组合约束

```text
A17387项目中的风阀控制图
第1页包含选择开关和继电器线圈的图纸
同时包含K1 K2 K3的控制原理图
```

每条查询标注：

```json
{
  "query": "...",
  "type": "semantic",
  "expected_result_ids": ["..."],
  "notes": "BM25可能不含完全相同措辞，验证Dense召回"
}
```

## 13. 测试计划

新增测试：

```text
tests/search/test_json_result_loader.py
tests/search/test_embedding.py
tests/search/test_qdrant_store.py
tests/search/test_hybrid_search.py
tests/search/test_search_degradation.py
tests/search/test_search_deduplication.py
tests/search/test_vector_rebuild.py
```

### 13.1 单元测试

覆盖：

- `steps/06` 优先于根 `result.json`。
- 缺少步骤文件时正确回退。
- 每种 chunk 的文本和 metadata。
- 稳定 point ID。
- Embedding 批处理和归一化。
- Qdrant upsert、search、delete。
- Dense hit 转换为 `SearchHit`。
- RRF 三路融合。
- 同一源图纸历史版本折叠。

测试不下载真实模型，使用固定维度 Fake Embedding。

### 13.2 集成测试

使用 Qdrant 内存模式：

1. 构造 3 份小型 JSON 结果。
2. 建立 SQLite 和向量索引。
3. 分别执行 BM25、Vector、Hybrid。
4. 验证三种模式返回不同的 `match_sources`。
5. 模拟向量后端异常，验证自动降级。

### 13.3 真实数据冒烟测试

对当前 `result/` 执行全量重建：

- 所有有效目录均可被扫描。
- 每个 SQLite chunk 对应一个 Qdrant point。
- 随机抽取 5 个 point，payload 与 SQLite 一致。
- Demo 查询集全部可执行。
- 搜索结果链接能打开对应识别结果。

## 14. 验收标准

### 14.1 功能验收

- 当前历史 JSON 无需重跑识别即可完成建库。
- `/api/search/health` 显示 SQLite、Embedding、Qdrant 可用。
- `hybrid` 查询返回 `dense > 0`。
- 结果 `match_sources` 能出现 `dense` 或 `bm25+dense`。
- 可以切换 BM25、Vector、Hybrid 进行现场对比。
- Qdrant 故障时 BM25 检索仍可使用。
- 索引可全量重建，也可针对单个 `result_id` 重建。

### 14.2 数据验收

- `SQLite search_chunks` 数量与 Qdrant point 数量一致。
- 最终元件来自 `steps/06-detected-components.json`。
- 最终组合来自 `steps/06-detected-combinations.json`。
- RAG 候选列表不被错误索引成最终元件。
- 自定义规则命中时可通过 `rule_layer=custom` 搜索和展示。
- 默认结果中同一源图纸不重复占据多个名次。

### 14.3 Demo 效果验收

在当前小样本上不设绝对召回率目标，要求至少证明：

1. 精确编号查询由 Exact/BM25 稳定召回。
2. 关键词查询由 BM25 稳定召回。
3. 至少 3 条措辞与原文不同的语义查询，Dense 能召回预期图纸。
4. Hybrid 的 Top-5 不弱于 BM25-only 和 Vector-only 的人工观察结果。
5. 每条结果可以解释命中来源和命中内容。

## 15. 实施步骤与预计工作量

### 阶段 A：JSON 统一加载与文档增强，0.5～1 天

- 实现 `JsonResultLoader`。
- 明确 `result.json` 与 `steps/06` 优先级。
- 增加元件组块、组合块和修正语义。
- 增加数据审计输出。

交付：

- 可从 16 个结果目录稳定生成统一 `DrawingDocument`。

### 阶段 B：Embedding 与 Qdrant Local，1～1.5 天

- 实现 Embedding 接口和 sentence-transformers 后端。
- 实现 Qdrant Local collection。
- 实现向量写入、删除、查询和健康检查。
- 增加 Fake Embedding 单元测试。

交付：

- 单独 Dense 查询可返回真实语义结果。

### 阶段 C：索引流程与混合召回，1 天

- 扩展 `DrawingIndexService`。
- 将 Dense 接入 `DrawingSearchService`。
- 完成 RRF 三路融合和降级。
- 增加历史版本折叠。

交付：

- `/api/search` 支持 `bm25`、`vector`、`hybrid`。

### 阶段 D：Demo 页面与评测，0.5～1 天

- 增加检索模式和命中来源展示。
- 建立 `demo_queries.json`。
- 执行全量重建和人工相关性检查。
- 整理现场演示脚本。

交付：

- 可现场演示的 BM25＋向量混合检索页面。

总工作量预估：

```text
3～4.5 人日
```

不包含首次下载模型所需网络时间。

## 16. 演示流程

演示前执行：

```powershell
python -m pip install -e ".[search]"
python scripts/rebuild_drawing_search_index.py --mode all --force
python -m uvicorn electronic_recognition.api:app --reload
```

浏览器打开：

```text
http://127.0.0.1:8000/search
```

建议演示顺序：

1. 查询图号 `CDDT-6-DZ-.07`，展示精确检索。
2. 查询“排烟风机”，展示 BM25。
3. 查询“可以手动自动切换的风阀控制回路”，展示 Dense。
4. 切换 BM25-only 与 Hybrid，对比排序和命中来源。
5. 查询“线圈和辅助触点属于同一设备的图纸”，展示组合规则语义块。
6. 展示 `/api/search/health` 和索引数量。
7. 临时关闭向量模式，展示 Exact＋BM25 降级能力。

## 17. 风险与处理

### 模型下载或 Python 环境不兼容

处理：

- 支持配置本地模型路径。
- 提供 Fake Embedding 仅用于自动测试。
- Demo 模型不可用时保持 BM25 页面可用。

### 中文短词 BM25 命中不稳定

处理：

- 保留 exact_terms。
- 使用领域同义词扩展。
- Dense 作为语义补充，不替代精确字段。

### 数据量过小导致效果评价偏差

处理：

- 明确 Demo 只验证链路。
- 使用固定查询集展示具体增益。
- 后续补充更多不同类型图纸再做正式 Recall/nDCG 评测。

### 历史结果重复

处理：

- 全部索引以保留历史。
- 默认按 `source_hash` 折叠。
- Debug 模式显示全部版本。

### JSON 结构版本不一致

处理：

- 使用统一 loader。
- 所有字段均允许缺省。
- 记录 loader/builder schema version。
- 对旧数据建立兼容性测试。

## 18. 完成定义

满足以下条件即视为 Demo 完成：

1. 当前 `result/` 下的有效 JSON 结果可一次性建立 SQLite 和 Qdrant 索引。
2. Qdrant 中存在与 SQLite chunk 对应的真实文本向量。
3. `dense_hits` 不再为空实现。
4. `/api/search` 能返回 Exact、BM25、Dense 和 RRF 融合结果。
5. `/search` 能展示语义命中来源、命中页和相关摘要。
6. Demo 查询集可以分别演示精确、关键词、语义和组合检索。
7. 向量服务异常时系统自动降级，现有识别和 BM25 检索不受影响。
8. 所有新增单元测试、集成测试及当前搜索测试通过。
