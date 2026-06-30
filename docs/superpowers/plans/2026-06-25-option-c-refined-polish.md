# Option C Refined 第二阶段精修 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在既有 `option-c-refined` 整页骨架上，继续完成两类改造：`视觉收口` 与 `组件去壳`，并优先把 `识别工作台` 精修到最接近静态稿的状态。

**Architecture:** 继续沿用上一轮 page-level 壳层，不改 API 和 composable，只针对页面模板、组件展示层和 CSS 进行精修。工作台作为主攻页会获得最严格的比例、密度和主次强化；知识库与检索页同步去组件化并压缩视觉密度。

**Tech Stack:** Vue 3, TypeScript, Vite, CSS, Vue Test Utils, Vitest

---

## 文件结构与职责

- `web/src/views/WorkbenchView.vue`
  - 进一步强化主画布优先级，压缩说明性内容，调整 `metric-grid + dense-grid` 比例
- `web/src/components/workbench/UploadPanel.vue`
  - 去上传组件卡片感，进一步融入 toolbar
- `web/src/components/workbench/ResultTabs.vue`
  - 去 tab 容器感，让预览区更像主画布
- `web/src/components/workbench/TaskStatusCard.vue`
  - 压缩成更轻的摘要侧 panel
- `web/src/views/KnowledgeView.vue`
  - 压缩左栏与两列主区比例，增强底部试运行板
- `web/src/components/knowledge/KnowledgeListPanel.vue`
  - 更像目录树/Facet 面板，减少列表组件感
- `web/src/components/knowledge/ComponentEditor.vue`
  - 减弱表单节块边界
- `web/src/components/knowledge/RuleEditor.vue`
  - 减弱节块拼接感，突出试运行输出区
- `web/src/views/SearchView.vue`
  - 压缩检索工具条和结果主区，强化主结果区
- `web/src/components/search/SearchToolbar.vue`
  - 更像条件面板内部内容，而不是独立表单卡
- `web/src/components/search/SearchResultList.vue`
  - 更像单一结果板
- `web/src/components/search/SearchResultCard.vue`
  - 压缩留白与 badge，贴近静态稿
- `web/src/app/styles/styles.css`
  - 调整共享 token、toolbar、metric、dense-grid、panel-title、button、field 密度
- `web/src/app/styles/knowledge.css`
  - 调整知识库左栏、两列主区和底部结果板
- `web/src/app/styles/search.css`
  - 调整条件栏、metric 和 result-card 样式
- `web/src/views/__tests__/WorkbenchView.test.ts`
- `web/src/views/__tests__/KnowledgeView.test.ts`
- `web/src/views/__tests__/SearchView.test.ts`
- `web/src/views/__tests__/ResultView.test.ts`
  - 保持当前结构回归与竞态验证

---

### Task 1: 先锁住工作台主次关系与精修目标

**Files:**
- Modify: `web/src/views/__tests__/WorkbenchView.test.ts`
- Modify: `web/src/components/workbench/TaskStatusCard.vue`
- Modify: `web/src/components/workbench/ResultTabs.vue`

- [ ] **Step 1: 先补一个工作台主次断言**

```ts
it('keeps preview as the primary panel and summary as the side panel', async () => {
  const router = createTestRouter()
  await router.push('/workbench')
  await router.isReady()

  const wrapper = mount(WorkbenchView, {
    global: { plugins: [router] },
  })

  expect(wrapper.find('.dense-grid .result-tabs').exists()).toBe(true)
  expect(wrapper.find('.dense-grid .result-summary-panel').exists()).toBe(true)
  expect(wrapper.find('.result-summary-panel .detail-row').exists()).toBe(true)
})
```

- [ ] **Step 2: 跑工作台测试确认新断言先失败或卡在旧实现**

Run: `pnpm vitest run src/views/__tests__/WorkbenchView.test.ts`

Expected: FAIL 或至少需要实现侧栏摘要 panel 与主预览区的精修结构。

- [ ] **Step 3: 调整摘要与结果区的模板命名，保证测试可定位**

```vue
<div class="dense-grid workbench-dense-grid">
  <ResultTabs class="workbench-primary-preview" ... />
  <TaskStatusCard class="result-summary-panel workbench-side-summary" ... />
</div>
```

- [ ] **Step 4: 再跑工作台测试确认通过**

Run: `pnpm vitest run src/views/__tests__/WorkbenchView.test.ts`

Expected: PASS。

- [ ] **Step 5: 提交该基线**

```bash
git add src/views/__tests__/WorkbenchView.test.ts src/components/workbench/TaskStatusCard.vue src/components/workbench/ResultTabs.vue
git commit -m "test: lock workbench primary preview hierarchy"
```

### Task 2: 精修工作台的视觉密度与组件去壳

**Files:**
- Modify: `web/src/views/WorkbenchView.vue`
- Modify: `web/src/components/workbench/UploadPanel.vue`
- Modify: `web/src/components/workbench/ResultTabs.vue`
- Modify: `web/src/components/workbench/TaskStatusCard.vue`
- Modify: `web/src/app/styles/styles.css`

- [ ] **Step 1: 压缩工作台工具条和指标区模板层级**

```vue
<div class="toolbar toolbar--workbench compact-toolbar">
  <UploadPanel @submitted="handleSubmitted" />
</div>

<div class="metric-grid metric-grid--workbench">
  <div class="metric compact-metric"><span>总页数</span><b>{{ previewPages.length || '--' }}</b></div>
  <div class="metric compact-metric"><span>检测元件</span><b>{{ components.length }}</b></div>
  <div class="metric compact-metric"><span>规则命中</span><b>{{ combinations.length }}</b></div>
  <div class="metric compact-metric"><span>异常告警</span><b class="warn">{{ warningCount }}</b></div>
</div>
```

- [ ] **Step 2: 让上传区彻底融入 toolbar**

```vue
<form class="toolbar-upload toolbar-upload--dense" @submit="handleSubmit">
  <div class="toolbar-group toolbar-group--inputs">...</div>
  <div class="toolbar-group toolbar-group--actions">...</div>
</form>
```

- [ ] **Step 3: 让 `ResultTabs` 更像主画布**

```vue
<section class="panel result-tabs workbench-primary-preview">
  <div class="panel-title panel-title--tight">
    <b>图纸预览</b>
    <span class="label">主画布</span>
  </div>
  <div class="tab-bar tab-bar--dense">...</div>
  <div class="tab-content tab-content--canvas">...</div>
</section>
```

- [ ] **Step 4: 让 `TaskStatusCard` 更像轻量摘要面板**

```vue
<section class="panel result-summary-panel workbench-side-summary">
  <div class="panel-title panel-title--tight">
    <b>结果摘要</b>
    <span class="label">辅助分析</span>
  </div>
  <div class="detail-row compact-row"><span>检测组件</span><b>{{ componentCount }}</b></div>
  <div class="detail-row compact-row"><span>规则命中</span><b>{{ combinationCount }}</b></div>
</section>
```

- [ ] **Step 5: 在共享样式中压缩工作台密度并强化左主右辅**

```css
.workbench-dense-grid {
  grid-template-columns: minmax(0, 1.34fr) minmax(250px, .66fr);
  gap: 8px;
}

.toolbar--workbench,
.toolbar-upload--dense {
  min-height: 40px;
}

.metric-grid--workbench .metric {
  min-height: 58px;
  padding: 8px 9px;
}

.workbench-primary-preview {
  min-height: 420px;
}

.workbench-side-summary {
  max-width: 100%;
}
```

- [ ] **Step 6: 跑工作台测试**

Run: `pnpm vitest run src/views/__tests__/WorkbenchView.test.ts`

Expected: PASS。

- [ ] **Step 7: 提交工作台精修**

```bash
git add src/views/WorkbenchView.vue src/components/workbench/UploadPanel.vue src/components/workbench/ResultTabs.vue src/components/workbench/TaskStatusCard.vue src/app/styles/styles.css
git commit -m "feat: polish workbench option c refined layout"
```

### Task 3: 精修知识库页并弱化组件感

**Files:**
- Modify: `web/src/views/KnowledgeView.vue`
- Modify: `web/src/components/knowledge/KnowledgeListPanel.vue`
- Modify: `web/src/components/knowledge/ComponentEditor.vue`
- Modify: `web/src/components/knowledge/RuleEditor.vue`
- Modify: `web/src/app/styles/knowledge.css`

- [ ] **Step 1: 压缩左栏和主区比例**

```css
.board--knowledge {
  grid-template-columns: 208px minmax(0, 1fr);
}

.knowledge-editor-grid {
  grid-template-columns: minmax(0, 1.28fr) minmax(260px, .72fr);
}
```

- [ ] **Step 2: 让目录树更像 facet/tree，而不是普通列表**

```vue
<div class="list-panel knowledge-tree-list">
  <button class="list-item tree-item" ...>
    <strong>{{ getLabel(item) }}</strong>
    <span>{{ item.id }}</span>
  </button>
</div>
```

- [ ] **Step 3: 让编辑器内容去节块拼接感**

```vue
<form class="editor-form editor-form--flat" data-form="component" @submit="handleSubmit">
  <section class="form-section form-section--flat">...</section>
  <section class="form-section form-section--flat">...</section>
</form>
```

- [ ] **Step 4: 让试运行结果更像底部输出板**

```vue
<section class="panel knowledge-run-panel">
  <div class="panel-title panel-title--tight">
    <b>试运行结果</b>
    <span class="label">output</span>
  </div>
  <div class="result-card">
    <h4>规则反馈</h4>
    <p>{{ message?.text || '执行校验或试运行后，这里回显结果摘要。' }}</p>
  </div>
</section>
```

- [ ] **Step 5: 跑知识库测试**

Run: `pnpm vitest run src/views/__tests__/KnowledgeView.test.ts`

Expected: PASS。

- [ ] **Step 6: 提交知识库精修**

```bash
git add src/views/KnowledgeView.vue src/components/knowledge/KnowledgeListPanel.vue src/components/knowledge/ComponentEditor.vue src/components/knowledge/RuleEditor.vue src/app/styles/knowledge.css
git commit -m "feat: polish knowledge option c refined layout"
```

### Task 4: 精修检索页并弱化组件感

**Files:**
- Modify: `web/src/views/SearchView.vue`
- Modify: `web/src/components/search/SearchToolbar.vue`
- Modify: `web/src/components/search/SearchResultList.vue`
- Modify: `web/src/components/search/SearchResultCard.vue`
- Modify: `web/src/app/styles/search.css`

- [ ] **Step 1: 收紧检索页工具条和条件栏**

```css
.board--search {
  grid-template-columns: 208px minmax(0, 1fr);
}

.search-conditions-panel {
  gap: 6px;
}

.search-toolbar-card .search-form {
  gap: 8px;
}
```

- [ ] **Step 2: 让条件栏更像 panel 内容**

```vue
<div class="search-toolbar-card panel search-toolbar-card--flat">
  <div class="panel-title panel-title--tight">
    <b id="searchTitle">检索条件</b>
    <span class="label">query</span>
  </div>
  <form class="search-form search-form--flat" @submit="handleSubmit">...</form>
</div>
```

- [ ] **Step 3: 收紧结果板与 result-card**

```vue
<section class="search-results-panel search-results-panel--flat">
  <div class="metric-grid metric-grid--search">...</div>
  <section class="panel">
    <div class="panel-title panel-title--tight">
      <b id="resultsTitle">结果列表</b>
      <span class="label">主结果区</span>
    </div>
  </section>
</section>
```

- [ ] **Step 4: 让结果卡更接近静态稿**

```css
.search-result-item {
  padding: 10px 11px;
}

.search-result-item h3,
.search-result-item h4 {
  font-size: 14px;
}

.search-result-item .badge {
  padding: 4px 7px;
}
```

- [ ] **Step 5: 跑检索页测试**

Run: `pnpm vitest run src/views/__tests__/SearchView.test.ts`

Expected: PASS。

- [ ] **Step 6: 提交检索页精修**

```bash
git add src/views/SearchView.vue src/components/search/SearchToolbar.vue src/components/search/SearchResultList.vue src/components/search/SearchResultCard.vue src/app/styles/search.css
git commit -m "feat: polish search option c refined layout"
```

### Task 5: 最终回归验证

**Files:**
- Modify: `web/src/views/__tests__/WorkbenchView.test.ts`
- Modify: `web/src/views/__tests__/KnowledgeView.test.ts`
- Modify: `web/src/views/__tests__/SearchView.test.ts`
- Modify: `web/src/views/__tests__/ResultView.test.ts`

- [ ] **Step 1: 跑四份视图测试全集**

Run: `pnpm vitest run src/views/__tests__/WorkbenchView.test.ts src/views/__tests__/KnowledgeView.test.ts src/views/__tests__/SearchView.test.ts src/views/__tests__/ResultView.test.ts`

Expected: PASS。

- [ ] **Step 2: 跑类型检查**

Run: `pnpm vue-tsc --noEmit`

Expected: PASS。

- [ ] **Step 3: 起本地预览**

Run: `pnpm dev --host 0.0.0.0`

Expected: Vite 启动成功，能打开 `/workbench`、`/knowledge`、`/search`。

- [ ] **Step 4: 核对第二阶段验收点**

```text
1. 工作台主画布明显强于摘要区
2. 工作台 toolbar / metric / tab / summary 密度明显更紧
3. 知识库目录树更像 facet/tree
4. 知识库底部试运行结果更像输出板
5. 检索条件区更紧凑
6. 检索结果卡更贴近静态稿 result-card
7. 三页整体组件拼接感继续减弱
```

- [ ] **Step 5: 最终提交**

```bash
git add src/views src/components src/app/styles
git commit -m "feat: polish option c refined ui surfaces"
```

## Self-Review

- **Spec coverage:** 已覆盖两类改造并行、工作台主攻、知识库与检索同步精修、继续维持测试与类型检查通过。
- **Placeholder scan:** 无 `TODO/TBD`；各任务都包含明确文件、命令和实现片段。
- **Type consistency:** 命名统一围绕 `workbench-primary-preview / result-summary-panel / board--knowledge / board--search / panel-title--tight / search-toolbar-card--flat` 这些展示层标识，不触碰现有 API 与 composable。
