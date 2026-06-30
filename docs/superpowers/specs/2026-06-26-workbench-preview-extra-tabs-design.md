# 识别工作台/结果页：图纸预览新增页签（方案 B）

## 背景

后端 pipeline 已输出三类结构化信息，但前端缺少展示入口：

- 图纸标签表（`component_table`）
- 控制与信号配置（`control_signal_configuration`）
- 图签信息（`title_block`）

目标是在不破坏现有“元件/组合/预览”体验的前提下，新增三个页签以展示上述信息，并支持字段缺失时的可解释空态与 JSON 兜底。

## 目标与非目标

### 目标

- 在 `ResultTabs` 现有三个页签基础上新增三个页签：
  - 图纸标签表
  - 控制/信号信息
  - 图签信息
- 新增页签同时出现在：
  - 识别工作台（`WorkbenchView`）
  - 识别结果页（`ResultView`）
- 展示策略采用方案 B：半结构化展示 + 原始 JSON 兜底
- 数据为空/缺失时不影响主流程，给出明确空态提示

### 非目标（后续迭代）

- 不在本次实现复杂交互（字段级高亮定位、跨页联动定位、复杂筛选/排序）
- 不强依赖后端 schema，避免因字段变动频繁改前端

## 数据映射

数据来自 `ResultDetail`：

- `result.component_table`
- `result.control_signal_configuration`
- `result.title_block`

类型定义当前为 `Record<string, unknown>`，但实际运行中可能出现数组或嵌套对象，因此 UI 层需要做运行时类型判断并兜底。

## 交互与信息结构（方案 B）

### 总体交互

- 页签固定显示 6 个（不做“有数据才显示”的条件渲染），避免用户认知跳变
- 每个新增页签都提供：
  - 结构化区域（能识别则表格/Key-Value）
  - “复制 JSON”按钮
  - “展开/收起原始 JSON”开关（默认收起）

### 页签 1：图纸标签表（`component_table`）

优先级：

1. **数组（Array）**：渲染为表格
   - 列来自“键集合”自动推导（最多 N 列，避免过宽）
2. **对象（Object）**：渲染为 Key-Value 列表（两列：key/value）
3. 其它：兜底为 JSON（结构化区显示空态）

空态：

- 标题：暂无图纸标签表
- 说明：后端未返回 `component_table` 或字段为空，不影响元件/预览查看。

### 页签 2：控制/信号信息（`control_signal_configuration`）

优先级：

1. 若识别到常见数组字段（例如 `signals`/`controls`）：
   - 双表布局（信号列表 / 控制配置）
2. 否则：
   - Key-Value 列表 + JSON 兜底

空态：

- 标题：暂无控制/信号信息
- 说明：后端未返回 `control_signal_configuration` 或字段为空，不影响元件/预览查看。

### 页签 3：图签信息（`title_block`）

优先级：

1. 对象（Object）：Key-Value 列表
2. 其它：兜底为 JSON

空态：

- 标题：未解析到图签信息
- 说明：后端未返回 `title_block` 或字段为空，不影响元件/预览查看。

## 组件与职责

### 修改点

- `web/src/components/workbench/ResultTabs.vue`
  - 扩展 tabs 配置
  - 新增三个 tab 的内容渲染
  - 新增 props：`componentTable`、`controlSignalConfiguration`、`titleBlock`
- `web/src/views/WorkbenchView.vue`
  - 向 `ResultTabs` 传入上述三个字段
- `web/src/views/ResultView.vue`
  - 向 `ResultTabs` 传入上述三个字段

### UI 组件拆分（建议）

为了避免 `ResultTabs` 过长，新增展示可拆成小组件：

- `ResultMetaJsonPanel`：复制 JSON / 展开 JSON 的通用壳
- `KeyValueList`：键值列表
- `AutoTable`：数组自动推导列的表格（带列数限制）

如果希望快速落地，也可以先内联实现，后续再拆分（但不做无关重构）。

## 可用性与降级策略

- 任意字段缺失/为 null/为空对象/空数组：
  - 结构化区展示空态
  - JSON 区仍可展开（为空则显示 `{}`/`[]`）
- 不做后端轮询额外请求：完全复用现有 result 加载/轮询结果

## 测试

### 组件测试

- `ResultTabs`：
  - 断言新增 3 个 tab 存在
  - 切换 tab 后出现对应标题/空态
  - JSON 展开/收起、复制按钮存在

### 视图测试

- `WorkbenchView.test.ts`：
  - mock 返回包含 `title_block`、`control_signal_configuration`、`component_table`
- `ResultView.test.ts`：
  - mock 返回包含三字段，确保渲染不报错

## 验收标准

- Workbench 与 Result 页的图纸预览区域均出现三个新增页签
- 字段为空时展示空态且不影响现有三页签
- 字段为对象/数组时至少能稳定渲染（表格或 key-value），并可展开查看原始 JSON
- 相关测试与 `vue-tsc --noEmit` 通过

