# Option C Refined 全量对齐设计

**日期**: 2026-06-25
**目标**: 将 `web/` 中的 `识别工作台`、`知识库管理`、`图纸检索` 三页，严格按 `option-c-refined.html` 的整页视觉骨架进行重构，并继续复用现有 Vue 业务逻辑与 API 数据流。

## 背景

当前 `web/` 已经完成一轮基于方案 C 的 Vue UI 改造，但仍然只是“方案 C 思路”，并未真正与已确认的静态稿 `d:\project\electronic_recognition\.superpowers\brainstorm\session-1782390878\content\option-c-refined.html` 做到整页级一致。

用户已明确要求：

- 严格按照 `option-c-refined.html` 调整
- 对齐范围为整页全量对齐

因此本轮目标不是“继续优化现有后台页”，而是把当前 Vue 页面重新装配进 `option-c-refined.html` 的页面框架中。

## 视觉基准

唯一视觉基准文件：

- `d:\project\electronic_recognition\.superpowers\brainstorm\session-1782390878\content\option-c-refined.html`

对齐优先级：

1. 页面外壳结构
2. 区块比例与密度
3. 控件尺寸与层级
4. 卡片和 panel 的圆角、边线、阴影
5. 文案与业务动作映射

允许灵活的部分：

- 少量按钮文案可保留现有业务语义
- 未实现后端能力的按钮继续置灰
- 组件内部表单字段可沿用当前 Vue 组件实现

## 总体架构

采用“双层壳模式”：

- 外层严格还原 `option-c-refined.html` 的页面结构
- 内层继续复用现有 Vue 组件、composable、API 调用与测试基线

即：

- 不推倒已有业务逻辑
- 重写 page-level template 与 page-level CSS
- 必要时通过 adapter 容器重排现有组件

## 三页统一结构

三页都统一改成以下结构：

```text
topbar
  wrap
    intro / hero / notes（如页面需要）
    screen
      screen-header
      canvas
        analysis-shell
          toolbar
          board
            panel / main / aside
```

统一视觉 token：

- 浅灰背景：`--bg`
- 半透明白色卡片：`--surface` / `--surface-soft`
- 细边线：`--line`
- 主强调色：`--accent`
- 大圆角容器：`--radius-lg`
- 中圆角 panel：`--radius-md`
- 小圆角控件：`--radius-sm`

统一顶层风格：

- 取消当前深色后台 header
- 改为 HTML 中的浅色 sticky `topbar`
- 页面切换按钮统一为 `chip`

## 页面设计

### 1. 识别工作台

严格对齐 `option-c-refined.html` 中的工作台 section：

- `screen-header` 仅承载页面标题和一句说明
- `analysis-shell` 为两层：
  - 上层 `toolbar`
  - 下层单列 `board`

主区结构：

- `metric-grid`
  - 总页数
  - 检测元件
  - 规则命中
  - 异常告警
- `dense-grid`
  - 左侧大图纸预览区
  - 右侧结果摘要区

业务映射：

- `UploadPanel` 作为输入来源嵌入 toolbar 或主区入口卡
- `TaskStatusCard` 改造成稿中的 `结果摘要`
- `ResultTabs` 负责承载预览、元件与组合结果，但视觉容器需要贴合稿中 panel

必须移除的现有感知：

- 独立后台式左侧栏
- “控制台/任务区”式布局语言

必须保留的能力：

- 上传图纸
- 提交识别
- 结果轮询
- 打开结果页
- 置灰的未来按钮

### 2. 知识库管理

严格对齐稿中的知识库 section：

- toolbar
- `board` 两栏布局：
  - 左栏 `220px` 左右的目录/Facet
  - 右侧主编辑区

右侧主编辑区结构：

- 上层 `dense-grid`
  - 规则编辑器
  - 素材对照
- 下层试运行结果

业务映射：

- `KnowledgeToolbar`、`KnowledgeListPanel` 放入左栏
- `ComponentEditor` / `RuleEditor` 放入主编辑区
- 试运行结果和图片预览需要按稿子的 panel 风格重新包装

必须移除的现有感知：

- 顶部 stats grid 主导的后台页样式
- 过强的“管理台”感

必须保留的能力：

- 组件与规则切换
- 加载详情
- 新建/保存/删除
- 图片上传
- 规则校验与试运行
- 版本对比按钮灰态

### 3. 图纸检索

严格对齐稿中的检索 section：

- toolbar
- `board` 两栏布局：
  - 左侧检索条件区
  - 右侧主结果区

右侧主结果区结构：

- 顶部 `metric-grid`
- 下方 `结果列表`

业务映射：

- `SearchToolbar` 映射到检索条件区
- `SearchResultList` 与 `SearchResultCard` 改造成稿中的 `result-card` 风格
- `SearchHealthPanel` 与 `SearchDemoQueries` 不再以独立辅助区存在；如保留，只能吸收到条件区内部，且不破坏整体版式

必须移除的现有感知：

- “检索辅助”独立区块
- 当前偏后台式的左栏卡片堆叠感

必须保留的能力：

- 查询提交
- 重建索引
- 结果渲染
- 保存查询灰态

## 组件边界策略

本轮不重写 API 与 composable：

- 保留 `useResultPolling`
- 保留知识库 API / search API
- 保留 `useSearch` / `useSearchHealth`

只允许在以下层面动刀：

- page-level template
- page-level CSS
- 容器级 adapter
- 少量展示型组件样式和结构

如果组件当前结构无法承接稿子：

- 优先外层包裹 adapter 容器
- 其次局部重排组件内部结构
- 不做无关业务逻辑重构

## 风险与控制

### 风险 1：视觉稿与现有交互结构不完全同构

处理：

- 以视觉稿为主
- 用 adapter 包装复用业务组件

### 风险 2：测试仍锁定旧结构

处理：

- 更新视图测试为 `option-c-refined.html` 对应结构断言
- 继续保留关键行为断言

### 风险 3：结果页竞态回归

处理：

- 保留当前已修复的请求代次校验
- 不在本轮视觉重构中回退该逻辑

## 验收标准

视为完成，需要同时满足：

- 三页整页结构肉眼可直接对应 `option-c-refined.html`
- 顶栏、screen、toolbar、board、panel、metric、result-card 的层级关系一致
- 控件尺寸、圆角、边框和间距整体接近 HTML 稿
- 未实现功能按钮保持灰态
- 已有 API 驱动能力不受影响
- 视图测试通过
- `pnpm vue-tsc --noEmit` 通过

## 实施范围

主要修改文件：

- `web/src/views/WorkbenchView.vue`
- `web/src/views/KnowledgeView.vue`
- `web/src/views/SearchView.vue`
- `web/src/components/workbench/*`
- `web/src/components/knowledge/*`
- `web/src/components/search/*`
- `web/src/app/styles/styles.css`
- `web/src/app/styles/knowledge.css`
- `web/src/app/styles/search.css`
- `web/src/views/__tests__/*`

## 非目标

本轮不做：

- 新增后端 API
- 改造识别/知识库/检索的数据协议
- 做新的权限模型
- 做额外的业务功能扩展

## 结论

本轮以 `option-c-refined.html` 为唯一视觉真值源，采用“双层壳模式”对现有 Vue 前端做整页级严格对齐。目标是让三页在视觉上回到用户确认的 C 调整版，同时保持现有业务能力和测试可验证性。
