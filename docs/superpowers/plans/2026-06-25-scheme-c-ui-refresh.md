# 方案C前端UI改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `web/` 中的识别工作台、知识库管理、图纸检索三页改造成贴合已确认的方案 C 视觉与 pipeline 结构的 Vue UI，并为未落地后端能力的按钮提供统一置灰策略。

**Architecture:** 保留现有 Vue 视图、composable 和 API 数据流，不重写业务逻辑；通过重构页面模板、局部拆分布局责任、重做页面级样式与组件状态，落地紧凑版方案 C。对没有后端支撑的视觉按钮采用前端 capability map 统一控制，避免“看得见点不了”之外的误导性交互。

**Tech Stack:** Vue 3, Vite, TypeScript, Vue Test Utils, Vitest, CSS

---

## 文件结构与职责

- `web/src/app/styles/styles.css`
  - 重做工作台共享壳层、顶栏、紧凑按钮、禁用态和方案 C 共用视觉 token
- `web/src/app/styles/knowledge.css`
  - 重做知识库页面布局、卡片、编辑区与图样对照样式
- `web/src/app/styles/search.css`
  - 重做检索条件区、结果列表与首屏比例，移除旧“辅助区”心智
- `web/src/app/uiCapabilities.ts`
  - 新增前端能力开关，定义需要先置灰的未来按钮
- `web/src/views/WorkbenchView.vue`
  - 改成“识别输入 -> 预览/结果摘要”结构，移除任务监控式区域
- `web/src/views/KnowledgeView.vue`
  - 改成“目录筛选 -> 编辑 -> 图样/试运行”结构，移除诊断侧栏
- `web/src/views/SearchView.vue`
  - 改成“检索条件 -> 结果列表”结构，移除检索辅助与详情调试区
- `web/src/components/workbench/UploadPanel.vue`
  - 收紧为 pipeline 入口卡片，支持禁用型辅助按钮
- `web/src/components/workbench/TaskStatusCard.vue`
  - 改造成紧凑结果摘要卡
- `web/src/components/workbench/ResultTabs.vue`
  - 强化主结果区视觉，适配方案 C 主体区
- `web/src/components/knowledge/KnowledgeToolbar.vue`
  - 调整为方案 C 紧凑工具条
- `web/src/components/knowledge/KnowledgeListPanel.vue`
  - 调整左栏列表密度
- `web/src/components/knowledge/ComponentEditor.vue`
  - 调整单元件编辑区结构与图片区按钮态
- `web/src/components/knowledge/RuleEditor.vue`
  - 调整规则编辑区、试运行区和按钮置灰
- `web/src/components/search/SearchToolbar.vue`
  - 将“过滤器”语义彻底切换为“检索条件”，收紧输入与动作区
- `web/src/views/__tests__/WorkbenchView.test.ts`
- `web/src/views/__tests__/KnowledgeView.test.ts`
- `web/src/views/__tests__/SearchView.test.ts`
  - 更新断言，覆盖方案 C 布局文案与按钮禁用态

## capability 约定

当前 API 已实现：

- 识别任务提交 `/analyze`
- 结果轮询 `/api/results/*`
- 知识库 CRUD、图片上传、规则校验、规则试运行
- 检索、检索健康、demo queries、索引重建

当前 UI 中若要体现但无后端支撑，应先置灰：

- 工作台中的“导出报告”“批量复核”等非现有 API 行为
- 知识库中的“版本对比”等纯视觉预留动作
- 检索页中的“保存查询”等未实现持久化动作

建议 capability 文件：

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

---

### Task 1: 建立方案C共享视觉基线与按钮能力开关

**Files:**
- Create: `web/src/app/uiCapabilities.ts`
- Modify: `web/src/app/styles/styles.css`
- Test: `web/src/views/__tests__/WorkbenchView.test.ts`
- Test: `web/src/views/__tests__/KnowledgeView.test.ts`
- Test: `web/src/views/__tests__/SearchView.test.ts`

- [ ] **Step 1: 先写失败测试，约束禁用按钮与方案C类名出现**

```ts
it('renders disabled future actions in workbench shell', async () => {
  const router = createTestRouter()
  await router.push('/workbench')
  await router.isReady()

  const wrapper = mount(WorkbenchView, {
    global: { plugins: [router] },
  })

  const disabledButtons = wrapper.findAll('button:disabled')
  expect(disabledButtons.some(button => button.text().includes('导出报告'))).toBe(true)
})

it('renders disabled version comparison action in knowledge view', async () => {
  const router = createTestRouter()
  await router.push('/knowledge')
  await router.isReady()

  const wrapper = mount(KnowledgeView, {
    global: { plugins: [router] },
  })

  expect(wrapper.find('[data-capability="compare-version"]').attributes('disabled')).toBeDefined()
})

it('renders disabled save-query action in search view', async () => {
  const router = createTestRouter()
  await router.push('/search')
  await router.isReady()

  const wrapper = mount(SearchView, {
    global: { plugins: [router] },
  })

  expect(wrapper.find('[data-capability="save-query"]').attributes('disabled')).toBeDefined()
})
```

- [ ] **Step 2: 运行测试，确认当前失败**

Run: `pnpm vitest run src/views/__tests__/WorkbenchView.test.ts src/views/__tests__/KnowledgeView.test.ts src/views/__tests__/SearchView.test.ts`

Expected: FAIL，提示找不到对应按钮或 `disabled` 断言失败。

- [ ] **Step 3: 新增 capability 文件并补充共享禁用态样式**

```ts
// web/src/app/uiCapabilities.ts
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

```css
/* web/src/app/styles/styles.css */
:root {
  --c-bg: #eef2f5;
  --c-surface: rgba(255,255,255,.92);
  --c-surface-soft: #f7f9fc;
  --c-line: #d8e0e8;
  --c-text: #243648;
  --c-muted: #6d8093;
  --c-accent: #255ecb;
  --c-accent-soft: rgba(37,94,203,.08);
}

body {
  background:
    radial-gradient(circle at top right, rgba(37,94,203,.05), transparent 18%),
    linear-gradient(180deg, rgba(255,255,255,.86), rgba(255,255,255,.86)),
    var(--c-bg);
  color: var(--c-text);
}

.app-header {
  min-height: 62px;
  padding: 12px 22px;
  background: rgba(23, 38, 55, .94);
}

.app-header h1 {
  font-size: 18px;
}

.app-header p {
  font-size: 10px;
}

.primary-button,
.secondary-button,
.ghost-button,
.danger-button,
.compact-action {
  min-height: 34px;
  padding: 7px 12px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 700;
}

button:disabled,
.button-disabled {
  cursor: not-allowed;
  opacity: .45;
  box-shadow: none;
}
```

- [ ] **Step 4: 跑测试确认 capability 与基础样式改动不报错**

Run: `pnpm vitest run src/views/__tests__/WorkbenchView.test.ts src/views/__tests__/KnowledgeView.test.ts src/views/__tests__/SearchView.test.ts`

Expected: 仍有 FAIL，但失败应转移到页面结构文案未更新，而不是缺 capability 文件或基础样式引用错误。

- [ ] **Step 5: 提交这一层基础设施**

```bash
git add web/src/app/uiCapabilities.ts web/src/app/styles/styles.css web/src/views/__tests__/WorkbenchView.test.ts web/src/views/__tests__/KnowledgeView.test.ts web/src/views/__tests__/SearchView.test.ts
git commit -m "feat: add scheme c ui capability baseline"
```

### Task 2: 改造识别工作台为方案C pipeline 结构

**Files:**
- Modify: `web/src/views/WorkbenchView.vue`
- Modify: `web/src/components/workbench/UploadPanel.vue`
- Modify: `web/src/components/workbench/TaskStatusCard.vue`
- Modify: `web/src/components/workbench/ResultTabs.vue`
- Modify: `web/src/app/styles/styles.css`
- Test: `web/src/views/__tests__/WorkbenchView.test.ts`

- [ ] **Step 1: 写失败测试，锁定新的 pipeline 文案和禁用动作**

```ts
it('renders scheme c workbench pipeline layout', async () => {
  const router = createTestRouter()
  await router.push('/workbench')
  await router.isReady()

  const wrapper = mount(WorkbenchView, {
    global: { plugins: [router] },
  })

  expect(wrapper.text()).toContain('识别输入')
  expect(wrapper.text()).toContain('图纸预览')
  expect(wrapper.text()).toContain('结果摘要')
  expect(wrapper.text()).not.toContain('当前任务')
  expect(wrapper.text()).not.toContain('任务工作区')
})
```

- [ ] **Step 2: 运行单测确认失败**

Run: `pnpm vitest run src/views/__tests__/WorkbenchView.test.ts`

Expected: FAIL，因为当前页面仍有“任务工作区/当前任务”。

- [ ] **Step 3: 重写 `WorkbenchView.vue` 的模板骨架**

```vue
<template>
  <header class="app-header app-header--scheme-c">
    <div>
      <p>Workbench</p>
      <h1>识别工作台</h1>
    </div>
    <div class="header-actions">
      <RouterLink class="knowledge-entry" to="/knowledge">知识库管理</RouterLink>
      <RouterLink class="knowledge-entry" to="/search">图纸检索</RouterLink>
    </div>
  </header>

  <main class="scheme-c-page scheme-c-workbench">
    <section class="scheme-c-toolbar">
      <div class="scheme-c-toolbar-group">
        <span class="scheme-c-pill">{{ resultId ? `结果 ${resultId}` : '等待识别任务' }}</span>
        <span class="scheme-c-pill">DPI 220</span>
      </div>
      <div class="scheme-c-toolbar-group">
        <button class="secondary-button" type="button" :disabled="!uiCapabilities.workbench.exportReport">导出报告</button>
      </div>
    </section>

    <section class="scheme-c-board scheme-c-board--single">
      <div class="scheme-c-main">
        <UploadPanel @submitted="handleSubmitted" />
        <TaskStatusCard :resultId="resultId" :status="status" :updatedAt="updatedAt" />
        <ResultTabs
          v-if="resultId && (loading || result)"
          :components="components"
          :combinations="combinations"
          :previewPages="previewPages"
          :activeTab="activeTab"
          @update:activeTab="activeTab = $event"
        />
        <div v-else class="scheme-c-empty">
          <h3>等待识别结果</h3>
          <p>上传图纸后，这里会直接展示图纸预览与结果摘要。</p>
        </div>
      </div>
    </section>
  </main>
</template>
```

- [ ] **Step 4: 重写工作台子组件结构**

```vue
<!-- web/src/components/workbench/UploadPanel.vue -->
<template>
  <section class="scheme-c-card scheme-c-card--input">
    <div class="section-heading">
      <p>INPUT</p>
      <h2>识别输入</h2>
    </div>
    <form class="upload-form" @submit="handleSubmit">
      <label class="upload-box" :class="{ 'has-file': !!file }">
        <span>{{ file ? file.name : '选择 PDF 或 PNG 文件' }}</span>
        <input type="file" accept=".pdf,.png" @change="onFileChange" :disabled="submitting" />
      </label>
      <div class="scheme-c-inline-actions">
        <button class="primary-button" type="submit" :disabled="!file || submitting">
          <span>{{ submitting ? '提交中...' : '开始识别' }}</span>
        </button>
        <button class="secondary-button" type="button" disabled data-capability="batch-review">批量复核</button>
      </div>
    </form>
  </section>
</template>
```

```vue
<!-- web/src/components/workbench/TaskStatusCard.vue -->
<template>
  <section class="scheme-c-card" v-if="resultId">
    <div class="section-heading">
      <p>SUMMARY</p>
      <h2>结果摘要</h2>
    </div>
    <div class="scheme-c-metric-grid">
      <article><span>任务 ID</span><strong>{{ resultId }}</strong></article>
      <article><span>状态</span><strong>{{ status === 'complete' ? '已完成' : status === 'failed' ? '已失败' : '运行中' }}</strong></article>
      <article><span>更新时间</span><strong>{{ updatedAt || '--' }}</strong></article>
    </div>
  </section>
</template>
```

- [ ] **Step 5: 用 CSS 做成紧凑版方案C工作台**

```css
.scheme-c-page {
  height: calc(100dvh - 62px);
  padding: 12px;
  display: grid;
  grid-template-rows: 44px 1fr;
  gap: 10px;
}

.scheme-c-toolbar,
.scheme-c-board,
.scheme-c-card {
  border: 1px solid var(--c-line);
  border-radius: 16px;
  background: var(--c-surface);
}

.scheme-c-board--single {
  padding: 10px;
}

.scheme-c-main {
  display: grid;
  gap: 10px;
}

.scheme-c-inline-actions {
  display: flex;
  gap: 8px;
}
```

- [ ] **Step 6: 跑工作台测试**

Run: `pnpm vitest run src/views/__tests__/WorkbenchView.test.ts`

Expected: PASS。

- [ ] **Step 7: 提交工作台改造**

```bash
git add web/src/views/WorkbenchView.vue web/src/components/workbench/UploadPanel.vue web/src/components/workbench/TaskStatusCard.vue web/src/components/workbench/ResultTabs.vue web/src/app/styles/styles.css web/src/views/__tests__/WorkbenchView.test.ts
git commit -m "feat: restyle workbench to scheme c pipeline layout"
```

### Task 3: 改造知识库管理为“目录-编辑-试运行”方案C结构

**Files:**
- Modify: `web/src/views/KnowledgeView.vue`
- Modify: `web/src/components/knowledge/KnowledgeToolbar.vue`
- Modify: `web/src/components/knowledge/KnowledgeListPanel.vue`
- Modify: `web/src/components/knowledge/ComponentEditor.vue`
- Modify: `web/src/components/knowledge/RuleEditor.vue`
- Modify: `web/src/app/styles/knowledge.css`
- Test: `web/src/views/__tests__/KnowledgeView.test.ts`

- [ ] **Step 1: 写失败测试，去掉旧 stats grid 和诊断概念**

```ts
it('renders scheme c knowledge workflow layout', async () => {
  const router = createTestRouter()
  await router.push('/knowledge')
  await router.isReady()

  const wrapper = mount(KnowledgeView, {
    global: { plugins: [router] },
  })

  expect(wrapper.text()).toContain('目录筛选')
  expect(wrapper.text()).toContain('规则编辑器')
  expect(wrapper.text()).toContain('试运行结果')
  expect(wrapper.text()).not.toContain('单元件总数')
})
```

- [ ] **Step 2: 运行知识库测试确认失败**

Run: `pnpm vitest run src/views/__tests__/KnowledgeView.test.ts`

Expected: FAIL，因为当前仍渲染 stats grid。

- [ ] **Step 3: 改写 `KnowledgeView.vue` 结构**

```vue
<template>
  <header class="app-header app-header--scheme-c">
    <div>
      <p>Knowledge</p>
      <h1>知识库管理</h1>
    </div>
    <div class="header-actions">
      <RouterLink class="knowledge-entry" to="/workbench">识别工作台</RouterLink>
      <RouterLink class="knowledge-entry" to="/search">图纸检索</RouterLink>
    </div>
  </header>

  <main class="scheme-c-page scheme-c-knowledge">
    <section class="scheme-c-toolbar">
      <div class="scheme-c-toolbar-group">
        <span class="scheme-c-pill">组件 {{ componentTotal }}</span>
        <span class="scheme-c-pill">规则 {{ ruleTotal }}</span>
      </div>
    </section>

    <section class="scheme-c-board scheme-c-board--knowledge">
      <aside class="scheme-c-sidebar">
        <KnowledgeToolbar v-model:activeKind="activeKind" @create="handleCreate" @refresh="refreshCatalog" />
        <div class="filter-card">
          <label>
            <span>目录筛选</span>
            <input v-model="searchText" placeholder="按 ID / 名称 / 类型筛选" />
          </label>
        </div>
        <KnowledgeListPanel ... />
      </aside>

      <section class="scheme-c-main-panel">
        <header class="editor-header">...</header>
        <p v-if="message" class="feedback" :class="message.type">{{ message.text }}</p>
        <div class="editor-body">...</div>
      </section>
    </section>
  </main>
</template>
```

- [ ] **Step 4: 改写子组件工具条和按钮置灰**

```vue
<!-- web/src/components/knowledge/KnowledgeToolbar.vue -->
<template>
  <div class="sidebar-toolbar scheme-c-toolbar-strip">
    <div class="kind-switch" role="tablist" aria-label="知识库类型">
      <button class="kind-tab" :class="{ active: activeKind === 'component' }" type="button" @click="emit('update:activeKind', 'component')">单元件</button>
      <button class="kind-tab" :class="{ active: activeKind === 'rule' }" type="button" @click="emit('update:activeKind', 'rule')">组合元件</button>
    </div>
    <button class="primary-button" type="button" @click="emit('create')">新建</button>
  </div>
</template>
```

```vue
<!-- web/src/components/knowledge/RuleEditor.vue -->
<div class="member-toolbar">
  <button class="ghost-button" data-action="validate-rule" type="button" @click="handleValidate(($event.currentTarget as HTMLButtonElement).form!)">校验规则</button>
  <button class="secondary-button" data-action="test-rule" type="button" @click="handleTest(($event.currentTarget as HTMLButtonElement).form!)">试运行</button>
  <button class="secondary-button" data-capability="compare-version" type="button" disabled>版本对比</button>
</div>
```

- [ ] **Step 5: 收紧知识库 CSS 到方案C**

```css
.scheme-c-board--knowledge {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 10px;
  padding: 10px;
}

.scheme-c-sidebar,
.scheme-c-main-panel {
  min-height: 0;
  border: 1px solid var(--c-line);
  border-radius: 16px;
  background: var(--c-surface-soft);
}

.scheme-c-sidebar {
  padding: 10px;
  display: grid;
  gap: 8px;
}
```

- [ ] **Step 6: 跑知识库测试**

Run: `pnpm vitest run src/views/__tests__/KnowledgeView.test.ts`

Expected: PASS。

- [ ] **Step 7: 提交知识库改造**

```bash
git add web/src/views/KnowledgeView.vue web/src/components/knowledge/KnowledgeToolbar.vue web/src/components/knowledge/KnowledgeListPanel.vue web/src/components/knowledge/ComponentEditor.vue web/src/components/knowledge/RuleEditor.vue web/src/app/styles/knowledge.css web/src/views/__tests__/KnowledgeView.test.ts
git commit -m "feat: restyle knowledge management to scheme c layout"
```

### Task 4: 改造图纸检索为“检索条件-结果列表”方案C结构

**Files:**
- Modify: `web/src/views/SearchView.vue`
- Modify: `web/src/components/search/SearchToolbar.vue`
- Modify: `web/src/app/styles/search.css`
- Test: `web/src/views/__tests__/SearchView.test.ts`

- [ ] **Step 1: 写失败测试，锁定“检索条件”结构与禁用保存按钮**

```ts
it('renders scheme c search layout', async () => {
  const router = createTestRouter()
  await router.push('/search')
  await router.isReady()

  const wrapper = mount(SearchView, {
    global: { plugins: [router] },
  })

  expect(wrapper.text()).toContain('检索条件')
  expect(wrapper.text()).not.toContain('检索辅助')
  expect(wrapper.find('[data-capability="save-query"]').attributes('disabled')).toBeDefined()
})
```

- [ ] **Step 2: 运行搜索测试确认失败**

Run: `pnpm vitest run src/views/__tests__/SearchView.test.ts`

Expected: FAIL，因为页面还包含“检索辅助”。

- [ ] **Step 3: 改写 `SearchView.vue`**

```vue
<template>
  <header class="app-header app-header--scheme-c">
    <div>
      <p>Search</p>
      <h1>图纸混合检索</h1>
    </div>
    <div class="header-actions">
      <RouterLink class="knowledge-entry" to="/workbench">识别工作台</RouterLink>
      <RouterLink class="knowledge-entry" to="/knowledge">知识库管理</RouterLink>
    </div>
  </header>

  <main class="scheme-c-page scheme-c-search">
    <section class="scheme-c-toolbar">
      <div class="scheme-c-toolbar-group">
        <span class="scheme-c-pill">{{ healthError ? '服务异常' : '检索就绪' }}</span>
        <span class="scheme-c-pill">总命中 {{ total }}</span>
      </div>
    </section>

    <section class="scheme-c-board scheme-c-board--search">
      <aside class="scheme-c-sidebar app-sidebar-compact">
        <SearchToolbar ref="toolbarRef" :loading="loading" @search="handleSearch" @rebuild="handleRebuild" @demoClick="handleDemoClick" />
        <p v-if="message" class="message" :class="message.type">{{ message.text }}</p>
        <p v-if="degraded" class="message info">{{ degradedReason || '当前检索链路处于降级状态' }}</p>
      </aside>

      <SearchResultList :items="items" :total="total" :debug="false" />
    </section>
  </main>
</template>
```

- [ ] **Step 4: 改写 `SearchToolbar.vue`，把未来动作置灰**

```vue
<template>
  <div class="search-toolbar-card" aria-labelledby="searchTitle">
    <div class="section-heading">
      <p>QUERY</p>
      <h2 id="searchTitle">检索条件</h2>
    </div>
    <form class="search-form" @submit="handleSubmit">
      ...
      <div class="search-actions">
        <button class="primary-button" type="submit" :disabled="loading">
          <span>{{ loading ? '检索中' : '开始检索' }}</span><i></i>
        </button>
        <div class="rebuild-actions">
          <select v-model="rebuildMode">...</select>
          <button class="secondary-button" type="button" @click="handleRebuild">重建索引</button>
          <button class="secondary-button" data-capability="save-query" type="button" disabled>保存查询</button>
        </div>
      </div>
    </form>
  </div>
</template>
```

- [ ] **Step 5: 收紧搜索页 CSS**

```css
.scheme-c-board--search {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 10px;
  padding: 10px;
}

.search-sidebar {
  padding: 0;
  background: transparent;
  box-shadow: none;
}

.search-toolbar-card {
  gap: 10px;
}

.search-form input,
.search-form select,
.mode-chip span {
  min-height: 34px;
  font-size: 12px;
}
```

- [ ] **Step 6: 跑搜索测试**

Run: `pnpm vitest run src/views/__tests__/SearchView.test.ts`

Expected: PASS。

- [ ] **Step 7: 提交搜索页改造**

```bash
git add web/src/views/SearchView.vue web/src/components/search/SearchToolbar.vue web/src/app/styles/search.css web/src/views/__tests__/SearchView.test.ts
git commit -m "feat: restyle search view to scheme c query layout"
```

### Task 5: 联合验证与清理

**Files:**
- Modify: `web/src/views/WorkbenchView.vue`
- Modify: `web/src/views/KnowledgeView.vue`
- Modify: `web/src/views/SearchView.vue`
- Modify: `web/src/app/styles/styles.css`
- Modify: `web/src/app/styles/knowledge.css`
- Modify: `web/src/app/styles/search.css`

- [ ] **Step 1: 运行视图测试全集**

Run: `pnpm vitest run src/views/__tests__/WorkbenchView.test.ts src/views/__tests__/KnowledgeView.test.ts src/views/__tests__/SearchView.test.ts`

Expected: PASS。

- [ ] **Step 2: 运行类型检查**

Run: `pnpm vue-tsc --noEmit`

Expected: 0 errors。

- [ ] **Step 3: 本地启动预览方案C改造结果**

Run: `pnpm dev`

Expected: 启动 Vite 开发服务器，打开 `/workbench`、`/knowledge`、`/search` 可看到统一的紧凑版方案 C 视觉。

- [ ] **Step 4: 手动验证关键流程**

```text
1. 工作台上传 PDF，确认“开始识别”正常提交，“导出报告”保持灰态
2. 知识库切换单元件/组合元件，确认“版本对比”灰态，“校验规则/试运行”正常
3. 检索页执行查询，确认“重建索引”正常，“保存查询”灰态
```

- [ ] **Step 5: 最终提交**

```bash
git add web/src/views web/src/components web/src/app/styles web/src/app/uiCapabilities.ts
git commit -m "feat: apply scheme c ui refresh across core views"
```

## Self-Review

- **Spec coverage:** 已覆盖三页方案 C 视觉落地、pipeline 对齐、未实现后端按钮置灰、视图测试更新。
- **Placeholder scan:** 无 `TODO/TBD`；每个任务都给出目标文件、示例代码和验证命令。
- **Type consistency:** capability 命名统一使用 `uiCapabilities`；三页统一使用 `scheme-c-*` 类名前缀，避免后续实现时出现命名漂移。

