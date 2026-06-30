# Option C Refined 全量对齐 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `web/` 中的 `识别工作台`、`知识库管理`、`图纸检索` 三页，严格按 `option-c-refined.html` 的整页视觉骨架改造，同时保留现有 Vue 组件、API 交互、灰态按钮策略与测试可验证性。

**Architecture:** 采用“双层壳模式”。外层页面模板和页面级 CSS 严格还原 `option-c-refined.html` 的 `topbar / screen / toolbar / board / panel` 体系；内层继续复用已有组件、composable 和 API 数据流，通过 adapter 容器完成布局映射，而不是重写业务逻辑。

**Tech Stack:** Vue 3, TypeScript, Vite, CSS, Vue Test Utils, Vitest

---

## 文件结构与职责

- `web/src/views/WorkbenchView.vue`
  - 改造成 `screen + canvas + analysis-shell` 的工作台整页壳层，映射静态稿中的 `metric-grid + dense-grid`
- `web/src/views/KnowledgeView.vue`
  - 改造成知识库整页壳层，映射静态稿中的 `220px 左栏 + 主编辑区 + 试运行结果`
- `web/src/views/SearchView.vue`
  - 改造成检索整页壳层，映射静态稿中的 `220px 条件栏 + metric-grid + 结果列表`
- `web/src/components/workbench/UploadPanel.vue`
  - 映射静态稿中的输入/动作区域，保持提交识别与灰态按钮
- `web/src/components/workbench/TaskStatusCard.vue`
  - 映射静态稿中的 `结果摘要` panel
- `web/src/components/workbench/ResultTabs.vue`
  - 映射静态稿中的主结果/预览展示区
- `web/src/components/knowledge/KnowledgeToolbar.vue`
  - 映射左栏顶部切换与操作条
- `web/src/components/knowledge/KnowledgeListPanel.vue`
  - 映射左栏目录树/Facet 区域
- `web/src/components/knowledge/ComponentEditor.vue`
  - 适配主编辑区 panel 视觉
- `web/src/components/knowledge/RuleEditor.vue`
  - 适配 `规则编辑器 / 试运行结果 / 灰态版本对比`
- `web/src/components/search/SearchToolbar.vue`
  - 映射检索条件区与 toolbar 动作
- `web/src/components/search/SearchResultList.vue`
  - 改造成静态稿 `结果列表` 外层结构
- `web/src/components/search/SearchResultCard.vue`
  - 改造成静态稿 `result-card` 风格
- `web/src/app/styles/styles.css`
  - 承载静态稿共享 token、topbar、screen、toolbar、panel、metric 样式
- `web/src/app/styles/knowledge.css`
  - 承载知识库页专属 grid 与 panel 样式
- `web/src/app/styles/search.css`
  - 承载检索页专属条件栏、metric、result-card 样式
- `web/src/views/__tests__/WorkbenchView.test.ts`
- `web/src/views/__tests__/KnowledgeView.test.ts`
- `web/src/views/__tests__/SearchView.test.ts`
  - 锁定 `option-c-refined.html` 对应结构和灰态动作
- `web/src/views/ResultView.vue`
- `web/src/views/__tests__/ResultView.test.ts`
  - 保留并验证已修复的请求竞态，不在视觉改造中回退

## 视觉基准

唯一视觉真值源：

- `d:/project/electronic_recognition/.superpowers/brainstorm/session-1782390878/content/option-c-refined.html`

本计划中的结构名与视觉术语，均以该 HTML 中的：

- `.topbar`
- `.wrap`
- `.screen`
- `.screen-header`
- `.canvas`
- `.analysis-shell`
- `.toolbar`
- `.board`
- `.panel`
- `.metric-grid`
- `.result-card`

为准。

---

### Task 1: 先把三页测试改成 option-c-refined 的结构断言

**Files:**
- Modify: `web/src/views/__tests__/WorkbenchView.test.ts`
- Modify: `web/src/views/__tests__/KnowledgeView.test.ts`
- Modify: `web/src/views/__tests__/SearchView.test.ts`

- [ ] **Step 1: 写失败断言，锁定工作台的整页骨架**

```ts
it('renders option c refined workbench shell', async () => {
  const router = createTestRouter()
  await router.push('/workbench')
  await router.isReady()

  const wrapper = mount(WorkbenchView, {
    global: { plugins: [router] },
  })

  expect(wrapper.find('.topbar').exists()).toBe(true)
  expect(wrapper.find('.screen').exists()).toBe(true)
  expect(wrapper.find('.analysis-shell').exists()).toBe(true)
  expect(wrapper.find('.toolbar').exists()).toBe(true)
  expect(wrapper.find('.board').exists()).toBe(true)
  expect(wrapper.text()).toContain('图纸预览')
  expect(wrapper.text()).toContain('结果摘要')
})
```

- [ ] **Step 2: 写失败断言，锁定知识库的整页骨架**

```ts
it('renders option c refined knowledge shell', async () => {
  const router = createTestRouter()
  await router.push('/knowledge')
  await router.isReady()

  const wrapper = mount(KnowledgeView, {
    global: { plugins: [router] },
  })

  expect(wrapper.find('.topbar').exists()).toBe(true)
  expect(wrapper.find('.screen').exists()).toBe(true)
  expect(wrapper.find('.board').exists()).toBe(true)
  expect(wrapper.text()).toContain('规则编辑器')
  expect(wrapper.text()).toContain('试运行结果')
  expect(wrapper.text()).toContain('目录树')
})
```

- [ ] **Step 3: 写失败断言，锁定检索页的整页骨架**

```ts
it('renders option c refined search shell', async () => {
  const router = createTestRouter()
  await router.push('/search')
  await router.isReady()

  const wrapper = mount(SearchView, {
    global: { plugins: [router] },
  })

  expect(wrapper.find('.topbar').exists()).toBe(true)
  expect(wrapper.find('.screen').exists()).toBe(true)
  expect(wrapper.find('.board').exists()).toBe(true)
  expect(wrapper.text()).toContain('检索条件')
  expect(wrapper.text()).toContain('结果列表')
  expect(wrapper.find('[data-capability="save-query"]').attributes('disabled')).toBeDefined()
})
```

- [ ] **Step 4: 运行三页测试并确认按预期失败**

Run: `pnpm vitest run src/views/__tests__/WorkbenchView.test.ts src/views/__tests__/KnowledgeView.test.ts src/views/__tests__/SearchView.test.ts`

Expected: FAIL，原因是当前页面还不是 `.topbar / .screen / .analysis-shell / .board` 结构。

- [ ] **Step 5: 提交测试基线改动**

```bash
git add src/views/__tests__/WorkbenchView.test.ts src/views/__tests__/KnowledgeView.test.ts src/views/__tests__/SearchView.test.ts
git commit -m "test: lock refined option c page shells"
```

### Task 2: 重建共享视觉骨架与 page-level token

**Files:**
- Modify: `web/src/app/styles/styles.css`
- Modify: `web/src/app/uiCapabilities.ts`

- [ ] **Step 1: 在共享样式中引入静态稿 token 和容器类**

```css
:root {
  --bg: #eef2f5;
  --surface: rgba(255,255,255,0.92);
  --surface-soft: rgba(247,249,252,0.95);
  --line: #d8e0e8;
  --line-strong: #c4d0dc;
  --text: #243648;
  --muted: #6d8093;
  --accent: #255ecb;
  --accent-soft: rgba(37, 94, 203, 0.09);
  --warn: #bf7a22;
  --shadow: 0 16px 38px rgba(26, 47, 74, 0.07);
  --radius-lg: 22px;
  --radius-md: 14px;
  --radius-sm: 11px;
}

.topbar { ... }
.wrap { ... }
.screen { ... }
.screen-header { ... }
.canvas { ... }
.analysis-shell { ... }
.toolbar { ... }
.toolbar-group { ... }
.panel { ... }
.metric-grid { ... }
.result-card { ... }
```

- [ ] **Step 2: 保持 capability 文件与灰态动作一致**

```ts
export const uiCapabilities = {
  workbench: {
    exportReport: false,
    batchReview: false,
  },
  knowledge: {
    compareVersion: false,
  },
  search: {
    saveQuery: false,
  },
} as const
```

- [ ] **Step 3: 运行诊断确保样式与 capability 文件无报错**

Run: `pnpm vue-tsc --noEmit`

Expected: PASS。

- [ ] **Step 4: 提交共享骨架改动**

```bash
git add src/app/styles/styles.css src/app/uiCapabilities.ts
git commit -m "feat: add option c refined shared shell styles"
```

### Task 3: 将识别工作台整页对齐到静态稿

**Files:**
- Modify: `web/src/views/WorkbenchView.vue`
- Modify: `web/src/components/workbench/UploadPanel.vue`
- Modify: `web/src/components/workbench/TaskStatusCard.vue`
- Modify: `web/src/components/workbench/ResultTabs.vue`
- Test: `web/src/views/__tests__/WorkbenchView.test.ts`

- [ ] **Step 1: 按静态稿重写工作台页面骨架**

```vue
<template>
  <div class="topbar">
    <div>
      <h1>识别工作台</h1>
      <p>工作台直接围绕识别 pipeline 组织：输入图纸、执行识别、查看预览和结果摘要。</p>
    </div>
    <div class="chips">
      <RouterLink class="chip active" to="/workbench">识别工作台</RouterLink>
      <RouterLink class="chip" to="/knowledge">知识库管理</RouterLink>
      <RouterLink class="chip" to="/search">图纸检索</RouterLink>
    </div>
  </div>

  <div class="wrap">
    <section class="screen">
      <div class="screen-header">...</div>
      <div class="canvas">
        <div class="analysis-shell">
          <div class="toolbar">...</div>
          <div class="board board--workbench-single">
            <main>
              <div class="metric-grid">...</div>
              <div class="dense-grid">
                <section class="panel">图纸预览</section>
                <section class="panel">结果摘要</section>
              </div>
            </main>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
```

- [ ] **Step 2: 把 `UploadPanel` 映射到静态稿的输入动作**

```vue
<div class="toolbar-group">
  <div class="control">{{ file ? file.name : '输入 本地文件' }}</div>
  <div class="control">DPI 220</div>
</div>
<div class="toolbar-group">
  <button class="button primary" type="submit">开始识别</button>
  <button class="button" type="button" disabled data-capability="batch-review">异常复核</button>
  <button class="button" type="button" disabled data-capability="export-report">导出</button>
</div>
```

- [ ] **Step 3: 把 `TaskStatusCard` 和 `ResultTabs` 适配到右侧摘要与主画布**

```vue
<section class="panel">
  <div class="panel-title"><b>结果摘要</b><span class="label">结构视图</span></div>
  <div class="detail-row"><span>检测组件</span><b>{{ componentCount }}</b></div>
  <div class="detail-row"><span>规则命中</span><b>{{ combinationCount }}</b></div>
  <div class="detail-row"><span>建议复核</span><b class="warn">{{ warningCount }}</b></div>
</section>
```

- [ ] **Step 4: 跑工作台测试确认通过**

Run: `pnpm vitest run src/views/__tests__/WorkbenchView.test.ts`

Expected: PASS。

- [ ] **Step 5: 提交工作台整页对齐**

```bash
git add src/views/WorkbenchView.vue src/components/workbench/UploadPanel.vue src/components/workbench/TaskStatusCard.vue src/components/workbench/ResultTabs.vue src/views/__tests__/WorkbenchView.test.ts
git commit -m "feat: align workbench to refined option c layout"
```

### Task 4: 将知识库管理整页对齐到静态稿

**Files:**
- Modify: `web/src/views/KnowledgeView.vue`
- Modify: `web/src/components/knowledge/KnowledgeToolbar.vue`
- Modify: `web/src/components/knowledge/KnowledgeListPanel.vue`
- Modify: `web/src/components/knowledge/ComponentEditor.vue`
- Modify: `web/src/components/knowledge/RuleEditor.vue`
- Modify: `web/src/app/styles/knowledge.css`
- Test: `web/src/views/__tests__/KnowledgeView.test.ts`

- [ ] **Step 1: 按静态稿重写知识库页面外壳**

```vue
<template>
  <div class="topbar">...</div>
  <div class="wrap">
    <section class="screen">
      <div class="screen-header">...</div>
      <div class="canvas">
        <div class="analysis-shell">
          <div class="toolbar">...</div>
          <div class="board board--knowledge">
            <aside class="panel">目录树</aside>
            <main>
              <div class="dense-grid">
                <section class="panel">规则编辑器</section>
                <section class="panel">素材对照</section>
              </div>
              <section class="panel">试运行结果</section>
            </main>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
```

- [ ] **Step 2: 将左栏与主编辑区适配进静态稿 panel**

```css
.board--knowledge {
  grid-template-columns: 220px minmax(0, 1fr);
}

.knowledge-tree-panel { ... }
.knowledge-editor-main { ... }
.knowledge-preview-panel { ... }
.knowledge-run-panel { ... }
```

- [ ] **Step 3: 给 `RuleEditor` 补上灰态 `版本对比` 并把试运行视觉收进 panel**

```vue
<button
  class="button"
  type="button"
  data-capability="compare-version"
  :disabled="!uiCapabilities.knowledge.compareVersion"
>
  版本对比
</button>
```

- [ ] **Step 4: 跑知识库测试确认通过**

Run: `pnpm vitest run src/views/__tests__/KnowledgeView.test.ts`

Expected: PASS。

- [ ] **Step 5: 提交知识库整页对齐**

```bash
git add src/views/KnowledgeView.vue src/components/knowledge/KnowledgeToolbar.vue src/components/knowledge/KnowledgeListPanel.vue src/components/knowledge/ComponentEditor.vue src/components/knowledge/RuleEditor.vue src/app/styles/knowledge.css src/views/__tests__/KnowledgeView.test.ts
git commit -m "feat: align knowledge page to refined option c layout"
```

### Task 5: 将图纸检索整页对齐到静态稿

**Files:**
- Modify: `web/src/views/SearchView.vue`
- Modify: `web/src/components/search/SearchToolbar.vue`
- Modify: `web/src/components/search/SearchResultList.vue`
- Modify: `web/src/components/search/SearchResultCard.vue`
- Modify: `web/src/app/styles/search.css`
- Test: `web/src/views/__tests__/SearchView.test.ts`

- [ ] **Step 1: 按静态稿重写检索页外壳**

```vue
<template>
  <div class="topbar">...</div>
  <div class="wrap">
    <section class="screen">
      <div class="screen-header">...</div>
      <div class="canvas">
        <div class="analysis-shell">
          <div class="toolbar">...</div>
          <div class="board board--search">
            <aside class="panel">检索条件</aside>
            <main>
              <div class="metric-grid">...</div>
              <section class="panel">结果列表</section>
            </main>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
```

- [ ] **Step 2: 将 `SearchToolbar` 映射为左栏条件区**

```vue
<div class="panel-title"><b>检索条件</b><span class="label">Query</span></div>
<div class="field">项目名称过滤</div>
<div class="field">页码 / 修订号 / 图纸类别</div>
<button class="button primary" type="submit">开始检索</button>
<button class="button" data-action="rebuild-index" type="button">重建索引</button>
<button class="button" data-capability="save-query" type="button" disabled>保存查询</button>
```

- [ ] **Step 3: 将 `SearchResultList` / `SearchResultCard` 改成静态稿 result-card**

```vue
<section class="panel">
  <div class="panel-title"><b>结果列表</b><span class="label">主结果区</span></div>
  <div class="result-card" v-for="item in items" :key="item.result_id">
    <h4>{{ item.drawing_title }}</h4>
    <p>{{ item.snippet }}</p>
    <div class="badge-row">
      <span class="badge">score {{ item.score.toFixed(2) }}</span>
    </div>
  </div>
</section>
```

- [ ] **Step 4: 跑检索页测试确认通过**

Run: `pnpm vitest run src/views/__tests__/SearchView.test.ts`

Expected: PASS。

- [ ] **Step 5: 提交检索页整页对齐**

```bash
git add src/views/SearchView.vue src/components/search/SearchToolbar.vue src/components/search/SearchResultList.vue src/components/search/SearchResultCard.vue src/app/styles/search.css src/views/__tests__/SearchView.test.ts
git commit -m "feat: align search page to refined option c layout"
```

### Task 6: 回归验证竞态修复并做最终收口

**Files:**
- Modify: `web/src/views/ResultView.vue`
- Test: `web/src/views/__tests__/ResultView.test.ts`
- Modify: `web/src/app/styles/styles.css`
- Modify: `web/src/app/styles/knowledge.css`
- Modify: `web/src/app/styles/search.css`

- [ ] **Step 1: 跑结果页竞态测试，确保视觉改造未破坏请求代次校验**

Run: `pnpm vitest run src/views/__tests__/ResultView.test.ts`

Expected: PASS。

- [ ] **Step 2: 跑四份视图测试全集**

Run: `pnpm vitest run src/views/__tests__/WorkbenchView.test.ts src/views/__tests__/KnowledgeView.test.ts src/views/__tests__/SearchView.test.ts src/views/__tests__/ResultView.test.ts`

Expected: PASS。

- [ ] **Step 3: 跑类型检查**

Run: `pnpm vue-tsc --noEmit`

Expected: PASS。

- [ ] **Step 4: 启动本地预览并逐页核对**

Run: `pnpm dev --host 0.0.0.0`

Expected: Vite 启动成功，手动打开：
- `/workbench`
- `/knowledge`
- `/search`

核对点：

```text
1. 顶栏是否为浅色 sticky topbar 而不是深色后台 header
2. screen / screen-header / canvas / toolbar / board 是否与静态稿层级一致
3. panel、metric、result-card 的比例和密度是否接近静态稿
4. 灰态按钮是否仍然不可点击
```

- [ ] **Step 5: 最终提交**

```bash
git add src/views src/components src/app/styles src/app/uiCapabilities.ts
git commit -m "feat: align core pages with refined option c design"
```

## Self-Review

- **Spec coverage:** 已覆盖三页整页对齐、静态稿唯一视觉基准、灰态按钮、业务组件复用与结果页竞态保护。
- **Placeholder scan:** 无 `TODO/TBD`；每个任务含文件、代码示例、命令与预期结果。
- **Type consistency:** 统一使用 `topbar / wrap / screen / screen-header / canvas / analysis-shell / toolbar / board / panel / result-card` 作为视觉壳层命名，避免命名漂移。
