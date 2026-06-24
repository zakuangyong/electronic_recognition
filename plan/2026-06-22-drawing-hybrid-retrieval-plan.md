# 图纸级 BM25/向量混合检索系统改造计划

## 1. 背景与目标

当前项目已能从电气 PDF/PNG 中产出：

- 图签信息。
- PDF 文字层。
- 元件表。
- 控制与信号配置。
- 识别元件及坐标。
- 组合元件/功能组合。
- 页面渲染图和识别步骤。

这些信息目前只保存在单次识别结果中，尚未形成可跨图纸检索的统一索引。本次改造建立图纸级混合检索系统，采用：

```text
SQLite FTS5
+ BGE-M3
+ Qdrant
+ RRF
+ 精确字段加权
```

核心目标：

1. 支持按图号、合同号、元件代号、型号等精确检索。
2. 支持按自然语言功能语义检索，例如“带热继电器保护的风机启动图”。
3. 同时利用 BM25 的关键词能力和向量检索的语义能力。
4. 以页面/功能块作为召回粒度，以图纸作为最终结果粒度。
5. 支持识别完成后的增量索引、历史结果重建和删除同步。
6. 检索索引故障不得影响原识别任务完成。

首期不包含：

- 图像向量检索。
- 跨编码器或大模型重排。
- 用户行为学习排序。
- 图纸与规程文档之间的关系图谱。
- 多节点高可用 Qdrant 集群。

## 2. 检索场景

首期必须覆盖以下查询类型：

### 2.1 精确标识查询

```text
A17387_1706
原理图号 0506
合同号 ABC-2025-18
KM1
FU-02
```

要求：

- 精确命中优先。
- 支持全角/半角、空格、连字符和大小写差异。
- 元件代号不能仅依赖中文分词或 trigram。

### 2.2 元件与型号查询

```text
包含施耐德断路器的图纸
查找型号 LC1D09 的接触器
含 QF1、KM1 和 FR1 的图纸
```

### 2.3 功能语义查询

```text
风机启停控制和运行指示
电动机直接启动及过载保护
PLC 远程关阀控制
带本地手动和自动模式切换的回路
```

### 2.4 组合约束查询

```text
版本 B 的风机启动图
只查项目 A17387 中包含两个接触器的图纸
查找第二页有端子排的控制原理图
```

### 2.5 结果解释

每条结果应展示：

- 图纸名称和文件名。
- 图号、版本、工程/系统名称。
- 命中页面。
- 命中元件或组合功能。
- BM25/向量/精确字段命中来源。
- 相关文本摘要。
- 原图页面预览入口。

## 3. 总体架构

```text
识别结果 result.json
  -> DrawingDocumentBuilder
  -> 字段规范化与检索文档生成
       ├─ 图纸父文档
       ├─ 页面子文档
       └─ 功能块子文档
  -> SQLite
       ├─ 权威元数据
       ├─ 索引状态
       ├─ 精确字段表
       └─ FTS5 BM25 索引
  -> BGE-M3 Embedding
  -> Qdrant Dense Vector

查询
  -> QueryNormalizer
  -> 精确字段候选
  -> FTS5 BM25 Top-N
  -> Qdrant Dense Top-N
  -> RRF 融合
  -> 精确字段加权与约束惩罚
  -> 按 drawing_id 聚合
  -> Top-K 图纸结果
```

设计原则：

1. SQLite 是检索元数据和索引状态的权威来源。
2. Qdrant 只保存向量与必要过滤字段，不作为唯一事实来源。
3. `result.json` 是识别事实来源，可以随时重建检索索引。
4. 搜索只读路径与索引写入路径分离。
5. 所有索引对象带 `schema_version` 和 `content_hash`。

## 4. 索引粒度

### 4.1 图纸父文档

每份识别结果生成一个父文档：

```json
{
  "drawing_id": "sha256:...",
  "result_id": "...",
  "filename": "A17387_1706_项目原理图_05.pdf",
  "drawing_number": "...",
  "drawing_title": "...",
  "project_name": "...",
  "system_name": "...",
  "contract_number": "...",
  "revision": "...",
  "page_count": 2,
  "component_codes": ["QF1", "KM1", "FR1", "M1"],
  "component_labels": ["断路器", "接触器", "热继电器", "电动机"],
  "component_types": ["保护器件", "控制器件"],
  "component_models": ["..."],
  "combination_names": ["电动机启动与保护组合"],
  "control_signals": ["自动", "就地/手动"],
  "search_text": "...",
  "source_hash": "...",
  "schema_version": 1
}
```

父文档负责：

- 图纸级展示。
- 精确字段过滤。
- 图纸级 BM25。
- 图纸级向量。
- 子文档聚合。

### 4.2 页面子文档

每页生成一个页面文档：

```json
{
  "chunk_id": "drawing-id:page:1",
  "drawing_id": "drawing-id",
  "chunk_type": "page",
  "page": 1,
  "region_type": "",
  "text": "第1页，包含QF1断路器、KM1接触器……",
  "component_codes": ["QF1", "KM1"],
  "combination_names": ["启停控制及状态指示组合"]
}
```

页面文档负责：

- 返回命中页。
- 避免整份多页图纸只有一个过长向量。
- 支持页面级语义查询。

### 4.3 功能块子文档

如果“版面/功能区域路由层”已上线，则为以下区域生成子文档：

- 标题栏。
- 元件表。
- 主回路。
- 控制回路。
- 端子表。
- 修订栏。

如果区域路由尚未上线，首期只生成：

- `title_block`
- `component_table`
- `detected_components`
- `detected_combinations`
- `page`

两项改造之间保持松耦合：检索系统不能依赖区域路由才能启动，但应预留 `region_id`、`region_type` 和 `bounds`。

## 5. 检索文档构建

新增 `DrawingDocumentBuilder`，从以下数据构建统一检索文档：

- `manifest.json`
- `result.json`
- `steps/00-document.json`
- 页面原始文字。
- 标题栏字段。
- 元件表行。
- 控制信号配置。
- 识别元件。
- 组合识别结果。
- 可选版面区域结果。

### 5.1 文本模板

不要直接把 JSON 序列化后送入 BM25 或 Embedding。应生成稳定的领域文本：

```text
图纸文件：A17387_1706_项目原理图_05.pdf
工程名称：……
系统名称：……
图纸名称：风机控制原理图
原理图号：……
合同号：……
版本：B
页数：2
元件：QF1 断路器；KM1 接触器；FR1 热继电器；M1 电动机
组合功能：电动机启动与保护；启停控制及状态指示
控制方式：自动；就地手动；PLC 关阀
```

元件表子文档：

```text
元件表，第1页。
QF1，断路器，型号……，数量1。
KM1，交流接触器，型号……，数量1。
```

组合功能子文档：

```text
第1页识别到电动机启动与保护组合。
成员：QF1 短路保护；KM1 接触器控制；FR1 过载保护；M1 电动机负载。
```

### 5.2 文本长度控制

- 父文档控制在可配置字符数内。
- 页面文本过长时按功能块或固定长度切分。
- 保留少量重叠，避免语义被截断。
- 元件代号列表不截断。
- 每个向量块必须带 `drawing_id` 和页面信息。

## 6. 字段规范化

新增 `SearchNormalizer`，索引和查询共用同一套规则。

### 6.1 通用规范化

- Unicode NFKC。
- 全角转半角。
- 英文字母大写。
- 连续空白折叠。
- 中文标点统一。
- 常见 OCR 字符混淆保守修正。

### 6.2 元件代号

需要同时保存：

- 原始值。
- 紧凑值。
- 分段值。

例如：

```text
KM-01/A1
```

转换为：

```json
{
  "raw": "KM-01/A1",
  "compact": "KM01A1",
  "device": "KM01",
  "terminal": "A1",
  "aliases": ["KM-01", "KM01", "KM 01"]
}
```

注意：

- `M1`、`KA` 等短代号不能只依赖 FTS5 trigram。
- 代号应写入精确字段表，并支持集合包含查询。
- OCR 易混字符修正只能在符合代号模式时启用，避免修改普通文本。

### 6.3 图号与合同号

保存：

- 原始字段。
- 去空格形式。
- 去分隔符形式。
- 前缀和数字段。

例如：

```text
A17387_1706
A17387-1706
A173871706
```

作为同一标识的别名进入精确字段表。

### 6.4 领域同义词

维护可配置同义词：

```json
{
  "电机": ["电动机"],
  "风机": ["通风机", "风扇电机"],
  "接触器": ["交流接触器"],
  "热继": ["热继电器", "过载继电器"],
  "空开": ["断路器", "空气开关"],
  "启停": ["启动 停止", "起停"]
}
```

同义词主要用于：

- BM25 查询扩展。
- Embedding 文本补充。

禁止无限扩展；每个词最多加入少量高置信度同义词。

## 7. SQLite 数据设计

数据库路径建议：

```text
data/search/drawings.db
```

### 7.1 主表

```sql
CREATE TABLE drawings (
    drawing_id TEXT PRIMARY KEY,
    result_id TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    drawing_number TEXT,
    drawing_title TEXT,
    project_name TEXT,
    system_name TEXT,
    contract_number TEXT,
    revision TEXT,
    page_count INTEGER NOT NULL DEFAULT 1,
    source_hash TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    indexed_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);
```

### 7.2 子文档表

```sql
CREATE TABLE search_chunks (
    chunk_id TEXT PRIMARY KEY,
    drawing_id TEXT NOT NULL,
    chunk_type TEXT NOT NULL,
    page INTEGER,
    region_id TEXT,
    region_type TEXT,
    bounds_json TEXT,
    title TEXT,
    text TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    FOREIGN KEY (drawing_id) REFERENCES drawings(drawing_id)
);
```

### 7.3 精确字段表

```sql
CREATE TABLE exact_terms (
    drawing_id TEXT NOT NULL,
    term_type TEXT NOT NULL,
    raw_value TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    page INTEGER,
    chunk_id TEXT,
    PRIMARY KEY (
        drawing_id,
        term_type,
        normalized_value,
        page,
        chunk_id
    )
);
```

`term_type` 示例：

```text
drawing_number
contract_number
component_code
component_model
revision
project_code
```

为 `term_type, normalized_value` 建联合索引。

### 7.4 索引任务表

```sql
CREATE TABLE index_jobs (
    job_id TEXT PRIMARY KEY,
    result_id TEXT NOT NULL,
    drawing_id TEXT,
    status TEXT NOT NULL,
    stage TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

状态：

```text
pending
building
bm25_complete
embedding
vector_complete
complete
failed
deleting
deleted
```

## 8. FTS5 BM25 设计

### 8.1 FTS 表

建议一个 FTS 表保存父文档和子文档：

```sql
CREATE VIRTUAL TABLE drawing_fts USING fts5(
    chunk_id UNINDEXED,
    drawing_id UNINDEXED,
    drawing_number,
    component_codes,
    title,
    project_system,
    combinations,
    component_text,
    full_text,
    tokenize='trigram'
);
```

使用 trigram 是为了降低中文分词依赖，但必须补充精确字段表处理短代号。

### 8.2 字段权重

建议初始权重：

| 字段 | 权重 |
|---|---:|
| `drawing_number` | 12 |
| `component_codes` | 10 |
| `title` | 8 |
| `project_system` | 6 |
| `combinations` | 5 |
| `component_text` | 4 |
| `full_text` | 1 |

权重必须进入配置，不硬编码在 SQL 字符串中。

### 8.3 BM25 召回

默认召回：

```text
Top 50 chunks
```

查询流程：

1. 规范化原查询。
2. 识别并移除危险 FTS 运算符。
3. 构建保守的 FTS 查询。
4. 对领域同义词做有限 OR 扩展。
5. 返回 BM25 排名、命中列和摘要。

FTS 查询解析失败时：

- 降级为转义后的普通词查询。
- 不得让整个搜索接口返回 500。

## 9. BGE-M3 Embedding

### 9.1 模型封装

新增统一接口：

```python
class EmbeddingBackend(Protocol):
    @property
    def dimension(self) -> int:
        ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...
```

首期实现 BGE-M3 本地推理后端。模型路径、设备和批大小全部配置化，不在代码中固定向量维度。

### 9.2 部署选项

支持：

- CPU 本地模型。
- GPU 本地模型。
- 内部 Embedding HTTP 服务。

建议将重依赖放入可选依赖组：

```toml
[project.optional-dependencies]
search = [
  "qdrant-client>=...",
  "FlagEmbedding>=..."
]
```

如果主服务不适合加载大模型，可将 Embedding 运行在单独进程中，主服务通过 HTTP 调用。

### 9.3 Embedding 文本

父文档、页面文档、功能块文档分别生成向量。Embedding 文本应包含明确字段标签，避免只有值：

```text
图纸名称：风机控制原理图。
系统名称：排风系统。
元件：QF1 断路器，KM1 接触器，FR1 热继电器。
功能：风机启动停止，过载保护，运行指示。
```

查询向量使用：

```text
用户检索电气工程图纸：{normalized_query}
```

是否添加此前缀应通过评测确定。

### 9.4 缓存

Embedding 缓存键：

```text
model_id
+ model_revision
+ embedding_template_version
+ normalized_text_hash
```

可存放在 SQLite 独立表或文件缓存中。重复重建索引时应避免重新计算未变化文本。

## 10. Qdrant 设计

### 10.1 Collection

建议 collection：

```text
electronic_drawing_chunks_v1
```

每个 point 对应一个父文档或子文档：

```json
{
  "id": "stable-uuid",
  "vector": [],
  "payload": {
    "chunk_id": "...",
    "drawing_id": "...",
    "result_id": "...",
    "chunk_type": "page",
    "page": 1,
    "region_type": "control_circuit",
    "revision": "B",
    "project_name": "...",
    "schema_version": 1,
    "content_hash": "..."
  }
}
```

### 10.2 Payload 索引

为以下字段创建 payload index：

- `drawing_id`
- `result_id`
- `chunk_type`
- `page`
- `region_type`
- `revision`
- `project_name`
- `schema_version`

### 10.3 一致性

SQLite 与 Qdrant 无法使用同一个事务，因此使用可恢复的分阶段状态：

1. SQLite 写入/更新文档、子文档和 FTS。
2. 任务状态更新为 `bm25_complete`。
3. 计算 Embedding。
4. Qdrant upsert。
5. 校验向量点数量和内容哈希。
6. 任务状态更新为 `complete`。

失败后可从最近阶段重试。检索默认只返回 `index_jobs.status=complete` 的图纸，避免半索引状态。

## 11. 查询解析

新增 `QueryNormalizer` 和轻量查询解析器，输出：

```json
{
  "raw_query": "查找 KM-1 接触器控制的 1# 风机图纸",
  "normalized_query": "KM1 接触器 控制 1号 风机 图纸",
  "exact_terms": [
    {"type": "component_code", "value": "KM1"}
  ],
  "keywords": ["接触器", "控制", "风机"],
  "filters": {},
  "expanded_terms": ["交流接触器", "通风机"]
}
```

首期解析规则：

- 元件代号正则。
- 图号/合同号模式。
- 版本表达。
- 页码表达。
- “包含、排除、只查”等简单约束。
- 领域同义词。

复杂查询无法解析时仍可正常进入 BM25 和向量召回。

## 12. 多路召回

每次查询并行执行：

1. 精确字段查询。
2. FTS5 BM25。
3. Qdrant Dense Vector。

默认候选数：

```text
Exact: 全部高置信度命中，最多 100
BM25: Top 50 chunks
Dense: Top 50 chunks
```

可根据数据规模调整。

### 12.1 精确字段候选

精确字段命中不直接替代混合检索，而是：

- 生成高优先候选。
- 为最终排序加权。
- 满足明确过滤条件。

例如查询只有 `A17387_1706` 时，图号完全匹配应稳定排在第一。

### 12.2 BM25 候选

返回：

- `chunk_id`
- `drawing_id`
- 排名
- 原始 BM25 值
- 命中字段
- 摘要

### 12.3 Dense 候选

返回：

- `chunk_id`
- `drawing_id`
- 排名
- 余弦相似度
- payload

## 13. RRF 融合与精确字段加权

### 13.1 RRF

首期使用 Reciprocal Rank Fusion：

```text
rrf(chunk) = Σ 1 / (k + rank_source(chunk))
```

初始：

```text
k = 60
```

来源：

- BM25。
- Dense。
- 可选精确字段排名。

不直接使用：

```text
0.5 * BM25 + 0.5 * cosine
```

因为两类分数尺度和分布不一致，首版直接线性融合不稳定。

### 13.2 精确字段加权

在 RRF 后加入可解释加权：

| 命中 | 初始加分 |
|---|---:|
| 图号完全匹配 | +0.25 |
| 合同号完全匹配 | +0.20 |
| 元件代号完全匹配 | +0.12 |
| 元件型号完全匹配 | +0.10 |
| 图纸名称短语匹配 | +0.08 |
| 工程/系统名称匹配 | +0.05 |
| 版本完全匹配 | +0.05 |
| 明确版本冲突 | -0.20 |
| 明确排除词命中 | -0.25 |

实际值必须通过评测集调优，并写入配置。

### 13.3 图纸聚合

BM25 和向量召回的是 chunks，最终返回 drawings。

建议聚合：

```text
drawing_score =
    best_chunk_score
    + 0.35 * second_chunk_score
    + 0.15 * third_chunk_score
    + exact_boost
```

限制：

- 同一图纸最多使用前三个 chunk。
- 同一页面大量相似 chunk 不能无限累加。
- 保留最高分 chunk 作为主命中解释。

### 13.4 排序稳定性

同分时依次使用：

1. 精确标识命中数。
2. 命中来源数量。
3. 最佳 chunk 分数。
4. 识别更新时间。
5. `drawing_id`，保证稳定排序。

## 14. API 设计

### 14.1 搜索接口

```http
POST /api/search
```

请求：

```json
{
  "query": "带热继电器保护的风机启动图",
  "limit": 20,
  "offset": 0,
  "filters": {
    "revision": "",
    "project_name": "",
    "page": null
  },
  "debug": false
}
```

响应：

```json
{
  "query": {
    "raw": "...",
    "normalized": "...",
    "exact_terms": []
  },
  "total": 12,
  "items": [
    {
      "drawing_id": "...",
      "result_id": "...",
      "filename": "...",
      "drawing_number": "...",
      "drawing_title": "...",
      "revision": "B",
      "score": 0.083,
      "matched_pages": [1],
      "matched_components": ["KM1", "FR1"],
      "matched_combinations": ["电动机启动与保护组合"],
      "snippet": "...",
      "match_sources": ["bm25", "dense", "exact"],
      "preview_url": "/api/results/.../pages/1"
    }
  ],
  "timing_ms": {
    "normalize": 2,
    "bm25": 8,
    "dense": 24,
    "fusion": 2,
    "total": 36
  }
}
```

### 14.2 索引接口

```http
POST /api/search/index/{result_id}
DELETE /api/search/index/{result_id}
POST /api/search/rebuild
GET /api/search/index-status
GET /api/search/index-status/{result_id}
```

`rebuild` 应作为后台任务，不阻塞 HTTP 请求。

### 14.3 健康检查

扩展 `/health` 或增加：

```http
GET /api/search/health
```

返回：

- SQLite 可用性。
- FTS5 可用性。
- Qdrant 可用性。
- Embedding 后端可用性。
- collection 向量维度。
- 完整索引图纸数。
- 失败任务数。

## 15. 前端设计

建议增加独立页面：

```text
/search
```

首期页面：

- 搜索框。
- 最近查询。
- 图号、版本、工程筛选。
- 结果卡片。
- 命中页面缩略图。
- 命中元件和组合标签。
- BM25/语义/精确命中来源提示。
- 点击跳转现有识别结果详情。

调试模式可额外展示：

- BM25 排名。
- Dense 排名。
- RRF 分数。
- 精确字段加权。
- 命中 chunk 文本。

普通用户默认不显示内部打分。

## 16. 与识别流程集成

### 16.1 识别完成后的异步索引

当前 `_persist_result()` 完成后触发索引任务：

```text
识别任务 complete
  -> result.json 已落盘
  -> 创建 index_job
  -> 后台构建索引
```

关键原则：

- 索引失败不改变识别任务的 `complete` 状态。
- `manifest.json` 可增加独立的 `index_status`。
- 允许用户手动重试。

示例：

```json
{
  "status": "complete",
  "index_status": "failed",
  "index_error": "Qdrant unavailable"
}
```

### 16.2 历史结果重建

新增：

```text
scripts/rebuild_drawing_search_index.py
```

功能：

- 扫描 `result/*/result.json`。
- 验证 manifest 状态。
- 计算源内容哈希。
- 跳过未变化结果。
- 支持 `--force`。
- 支持单个 result ID。
- 支持只建 BM25 或只补向量。
- 输出成功、跳过、失败统计。

### 16.3 删除和重新识别

- 删除识别结果时同步进入索引删除队列。
- 同一 `result_id` 重建时 upsert。
- 同一源文件不同识别版本默认视为不同结果；后续可按源文件哈希折叠。
- Qdrant 删除失败时记录任务并重试，不立即删除 SQLite 的失败证据。

## 17. 配置

在 `Settings` 或独立 `SearchSettings` 中增加：

```text
ER_SEARCH_ENABLED=true
ER_SEARCH_SQLITE_PATH=data/search/drawings.db
ER_SEARCH_QDRANT_URL=http://127.0.0.1:6333
ER_SEARCH_QDRANT_API_KEY=
ER_SEARCH_COLLECTION=electronic_drawing_chunks_v1
ER_SEARCH_EMBEDDING_BACKEND=local
ER_SEARCH_EMBEDDING_MODEL=BAAI/bge-m3
ER_SEARCH_EMBEDDING_MODEL_PATH=
ER_SEARCH_EMBEDDING_DEVICE=cpu
ER_SEARCH_EMBEDDING_BATCH_SIZE=8
ER_SEARCH_BM25_LIMIT=50
ER_SEARCH_VECTOR_LIMIT=50
ER_SEARCH_RRF_K=60
ER_SEARCH_RESULT_LIMIT=20
ER_SEARCH_AUTO_INDEX=true
ER_SEARCH_EXACT_BOOST_CONFIG=data/index/search_weights.json
```

Embedding 模型路径为空且无法下载时，应明确报错并允许 BM25-only 模式运行。

## 18. 代码结构

建议新增：

```text
src/electronic_recognition/search/
  __init__.py
  models.py
  settings.py
  normalizer.py
  document_builder.py
  sqlite_store.py
  fts_store.py
  embedding.py
  qdrant_store.py
  index_service.py
  query_parser.py
  fusion.py
  search_service.py
  api_models.py

scripts/
  rebuild_drawing_search_index.py
  evaluate_drawing_search.py

data/search/
  .gitkeep

data/index/
  search_synonyms.json
  search_weights.json
```

现有文件改动：

- `api.py`
  - 注册搜索 API 和异步索引任务。
- `config.py`
  - 加载搜索配置。
- `models.py`
  - 如有需要增加索引状态字段，不耦合 Qdrant 类型。
- `pyproject.toml`
  - 增加搜索可选依赖和脚本入口。
- `static/index.html`
  - 增加图纸检索入口。
- 新增 `static/search.html`、`search.js`、`search.css`。

## 19. 索引版本管理

每个索引对象记录：

- `schema_version`
- `builder_version`
- `normalizer_version`
- `embedding_model_id`
- `embedding_model_revision`
- `embedding_template_version`
- `content_hash`

需要重建的情况：

- 检索字段结构变化。
- 规范化规则变化。
- Embedding 模型或模板变化。
- 区域路由加入新的 chunk 类型。

Qdrant collection 不直接原地切换不同维度向量。模型维度变化时：

1. 创建新 collection。
2. 后台重建。
3. 校验数量和查询结果。
4. 配置切换别名或 collection 名。
5. 保留旧 collection 一段时间后删除。

## 20. 测试计划

### 20.1 单元测试

新增：

```text
tests/search/test_normalizer.py
tests/search/test_document_builder.py
tests/search/test_fts_store.py
tests/search/test_exact_terms.py
tests/search/test_fusion.py
tests/search/test_drawing_aggregation.py
tests/search/test_index_service.py
tests/search/test_search_api.py
```

覆盖：

- 图号和元件代号规范化。
- 中文 trigram 查询。
- 两字符代号精确匹配。
- 父文档和子文档生成。
- RRF 排名计算。
- 精确字段加权。
- 版本冲突惩罚。
- 同图纸多 chunk 聚合。
- Qdrant 故障时 BM25 降级。
- Embedding 故障时索引任务可重试。
- 重复索引幂等。
- 删除同步。

### 20.2 集成测试

使用测试容器或本地 Qdrant：

1. 导入 10-20 个固定识别结果。
2. 建立 SQLite 和 Qdrant 索引。
3. 执行精确、关键词、语义和组合查询。
4. 验证命中图纸、页面和解释。
5. 模拟 Qdrant 下线，验证 BM25-only 降级。
6. 模拟 SQLite 锁和索引重试。

### 20.3 性能测试

至少测试：

- 1,000 份图纸。
- 10,000 份图纸。
- 每份 1-10 页。

关注：

- 索引吞吐。
- Embedding 吞吐。
- SQLite 文件大小。
- Qdrant 向量数量和存储。
- P50/P95 查询耗时。
- 并发查询时的 SQLite 锁竞争。

## 21. 检索评测

### 21.1 查询集

由实际用户整理至少 100 条查询：

| 类型 | 数量建议 |
|---|---:|
| 图号/合同号精确查询 | 20 |
| 元件代号/型号查询 | 20 |
| 元件组合查询 | 20 |
| 功能语义查询 | 25 |
| 多条件查询 | 15 |

每条查询标注：

- 高度相关图纸。
- 部分相关图纸。
- 不相关图纸。

使用 `2/1/0` 相关度。

### 21.2 对比实验

必须比较：

1. Exact-only。
2. BM25-only。
3. Dense-only。
4. BM25 + Dense RRF。
5. BM25 + Dense RRF + Exact Boost。

指标：

- Success@1。
- Success@5。
- Recall@10。
- MRR@10。
- nDCG@10。
- P50/P95 延迟。

### 21.3 首期验收指标

| 指标 | 目标 |
|---|---:|
| 图号完全匹配 Success@1 | 99% 以上 |
| 元件代号查询 Success@5 | 95% 以上 |
| 混合查询 Recall@10 | 比 BM25-only 提高至少 10% |
| 混合查询 nDCG@10 | 不低于 BM25-only 和 Dense-only |
| 10,000 图纸 P95 查询耗时 | 500ms 以内，不含首次模型加载 |
| 增量索引成功率 | 99% 以上 |
| Qdrant 故障时 BM25 降级 | 可用 |

## 22. 分阶段实施

### 阶段 0：数据审计与评测集

任务：

1. 审计历史 `result/` 数据完整性。
2. 明确 `drawing_id` 和重复图纸策略。
3. 建立 100 条真实查询和相关性标注。
4. 固定评测脚本和指标。

### 阶段 1：SQLite 元数据、精确字段和 BM25

任务：

1. 实现 `DrawingDocumentBuilder`。
2. 实现规范化和精确字段表。
3. 建立 FTS5 索引。
4. 提供 BM25-only API。
5. 提供历史重建脚本。

该阶段即可上线一个可用的图纸关键词检索。

### 阶段 2：BGE-M3 与 Qdrant

任务：

1. 部署 Qdrant。
2. 封装 Embedding 后端。
3. 建立父文档和子文档向量。
4. 增加向量召回。
5. 支持 Embedding 缓存和增量更新。

### 阶段 3：RRF 与精确加权

任务：

1. 并行多路召回。
2. 实现 RRF。
3. 实现精确字段加权和约束惩罚。
4. 实现图纸聚合和结果解释。
5. 在评测集上调优。

### 阶段 4：前端与识别自动索引

任务：

1. 增加 `/search` 页面。
2. 识别完成后异步索引。
3. 增加索引状态和重试。
4. 支持从搜索结果跳转到识别页面和命中页。

### 阶段 5：区域块增强

在版面/功能区域路由层上线后：

1. 增加主回路、控制回路、端子表等 chunk。
2. 重建相应向量。
3. 对比页面级与区域级检索效果。
4. 保留旧 schema 直到新索引通过验收。

## 23. 降级与容错

### 23.1 Qdrant 不可用

- 搜索降级为 Exact + BM25。
- 响应增加 `degraded: true`。
- 不返回 500，除非 SQLite 也不可用。

### 23.2 Embedding 后端不可用

- 新索引任务停留在可重试状态。
- 已有 Qdrant 向量仍可查询。
- BM25 索引仍可更新并提供结果。

### 23.3 SQLite 不可用或损坏

- 搜索返回明确的服务不可用。
- 不允许只依赖 Qdrant 返回缺少权威元数据的结果。
- 可通过历史 `result.json` 重建数据库。

### 23.4 半完成索引

- 只返回状态为 `complete` 的图纸。
- 后台任务定期扫描并重试 `failed` 或长时间未完成任务。

## 24. 安全与运维

- Qdrant 默认只监听内网或本机。
- API Key 不写入代码或日志。
- 用户查询日志需要限制保存周期。
- 搜索摘要必须来自已识别文档，不允许模型生成不存在的字段。
- Embedding 模型下载应支持离线模型路径和固定 revision。
- SQLite 定期备份，但必须保留从 `result.json` 全量重建能力。
- 提供索引数量、失败任务、查询延迟和降级次数监控。

## 25. 发布与回滚

发布顺序：

1. BM25-only 内部试用。
2. 接入 Qdrant 和 Dense，但不影响默认排序。
3. 开启 RRF，保留 BM25-only 对照参数。
4. 开启精确字段加权。
5. 开启识别完成后的自动索引。
6. 开放前端检索入口。

回滚：

- `ER_SEARCH_ENABLED=false` 关闭检索 API 和自动索引。
- `ER_SEARCH_MODE=bm25` 跳过 Qdrant。
- 保留 SQLite 和 Qdrant 数据，不在回滚时删除。
- 旧识别流程完全不依赖检索系统。

## 26. 完成定义

满足以下条件视为首期完成：

1. 历史识别结果可以批量重建 SQLite FTS5 和 Qdrant 索引。
2. 新识别结果可以异步增量索引。
3. 支持 Exact、BM25、Dense 三路召回。
4. 支持 RRF、精确字段加权和图纸级聚合。
5. 搜索结果包含命中页面、命中字段、摘要和可解释来源。
6. 图号完全匹配 Success@1 达到 99%。
7. 混合检索 Recall@10 相对 BM25-only 提高至少 10%。
8. Qdrant 或 Embedding 故障时可降级为 Exact + BM25。
9. 索引失败不影响识别任务完成。
10. 所有新增单元测试、集成测试和检索评测通过。

