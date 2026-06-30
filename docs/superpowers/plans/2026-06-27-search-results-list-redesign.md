# 图纸检索结果列表重设计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `图纸检索` 页的结果区重构为真正的检索结果列表，并将主动作改为“打开图纸”，通过悬浮大预览层承接图纸浏览与命中页定位。

**Architecture:** 保留现有 `SearchView -> SearchResultList -> SearchResultCard -> useSearch/api` 数据链路，不改后端协议，只重组页面头、结果卡信息层级和交互组件。新增一个前端预览悬浮层组件，由 `SearchView` 持有打开状态和当前选中结果，`SearchResultCard` 通过事件上抛触发预览。

**Tech Stack:** Vue 3 `script setup`、Vue Router、Vitest、Vue Test Utils、现有 `web/src/app/styles/search.css`

---

## File Map

- Modify: `web/src/views/SearchView.vue`
  - 管理当前查询结果头、打开预览层状态、选中结果与预览关闭逻辑
- Modify: `web/src/components/search/SearchResultList.vue`
  - 将 `metric-grid` 改成查询结果信息条，并向下传递卡片动作事件
- Modify: `web/src/components/search/SearchResultCard.vue`
  - 将卡片重构为“序号 + 标题 + 相关度 + 命中理由 + 轻动作带”的检索结果流
- Create: `web/src/components/search/SearchPreviewModal.vue`
  - 悬浮大预览层，负责显示图纸标题、命中页、预览 iframe/嵌入容器和页码导航
- Modify: `web/src/composables/useSearch.ts`
  - 暴露结果头需要的检索上下文，例如 `lastQuery`
- Modify: `web/src/views/__tests__/SearchView.test.ts`
  - 更新旧断言，覆盖“打开图纸”“查询结果头”“悬浮预览层”集成行为
- Create: `web/src/components/search/__tests__/SearchResultCard.test.ts`
  - 覆盖卡片文案层级与按钮事件
- Create: `web/src/components/search/__tests__/SearchPreviewModal.test.ts`
  - 覆盖预览层打开、关闭、页码切换与空页码兜底
- Modify: `web/src/app/styles/search.css`
  - 收口结果头、结果卡、动作带与预览层样式

### Task 1: 重建查询结果头与测试基线

**Files:**
- Modify: `d:\project\electronic_recognition\web\src\views\SearchView.vue`
- Modify: `d:\project\electronic_recognition\web\src\components\search\SearchResultList.vue`
- Modify: `d:\project\electronic_recognition\web\src\composables\useSearch.ts`
- Test: `d:\project\electronic_recognition\web\src\views\__tests__\SearchView.test.ts`

- [ ] **Step 1: 写失败测试，锁定新的结果头语义**

```ts
it('renders query result header instead of shell metrics after search', async () => {
  const router = createTestRouter()
  await router.push('/search')
  await router.isReady()

  const wrapper = mount(SearchView, {
    global: { plugins: [router] },
  })

  await flushPromises()
  await wrapper.find('input[type="search"]').setValue('thermal overload fan')
  await wrapper.find('form.search-form').trigger('submit')
  await flushPromises()

  expect(wrapper.text()).toContain('查询')
  expect(wrapper.text()).toContain('thermal overload fan')
  expect(wrapper.text()).toContain('找到 1 条结果')
  expect(wrapper.text()).toContain('排序')
  expect(wrapper.text()).not.toContain('目标区域')
  expect(wrapper.text()).not.toContain('主结果区')
  expect(wrapper.text()).not.toContain('standard')
})
```

- [ ] **Step 2: 运行单测，确认旧实现失败**

Run:

```bash
pnpm vitest run src/views/__tests__/SearchView.test.ts -t "renders query result header instead of shell metrics after search"
```

Expected:

```text
FAIL
Expected text to contain "查询"
Received content still contains "目标区域" / "standard"
```

- [ ] **Step 3: 在 `useSearch.ts` 暴露结果头所需的查询上下文**

```ts
export function useSearch() {
  const loading = ref(false)
  const items = ref<SearchResultItem[]>([])
  const total = ref(0)
  const lastQuery = ref('')
  const retrievalMode = ref('')
  const degraded = ref(false)
  const degradedReason = ref('')

  async function submitSearch(payload: SearchQuery): Promise<SearchResponse | null> {
    loading.value = true
    try {
      const result = await searchDrawings(payload)
      items.value = result.items ?? []
      total.value = result.total ?? 0
      retrievalMode.value = result.retrieval_mode ?? ''
      degraded.value = result.degraded ?? false
      degradedReason.value = result.degraded_reason ?? ''
      lastQuery.value = payload.query.trim()
      return result
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    items,
    total,
    lastQuery,
    retrievalMode,
    degraded,
    degradedReason,
    submitSearch,
  }
}
```

- [ ] **Step 4: 将 `SearchResultList.vue` 的顶部 `metric-grid` 改成查询结果头**

```vue
<script setup lang="ts">
import type { SearchResultItem } from '../../types/search'
import SearchResultCard from './SearchResultCard.vue'

defineProps<{
  items: SearchResultItem[]
  total: number
  query: string
  retrievalMode: string
}>()

const emit = defineEmits<{
  openPreview: [item: SearchResultItem]
}>()
</script>

<template>
  <section class="search-results-panel search-results-panel--stream" aria-labelledby="resultsTitle">
    <div class="search-results-summary">
      <div class="summary-main">
        <b id="resultsTitle">查询结果</b>
        <span v-if="query">查询：{{ query }}</span>
        <span>找到 {{ total }} 条结果</span>
        <span>排序：相关度优先</span>
      </div>
      <div class="summary-filters">
        <span class="summary-chip summary-chip--active">全部结果</span>
        <span class="summary-chip">精确命中优先</span>
        <span class="summary-chip">语义命中优先</span>
        <span class="summary-chip">模式 {{ retrievalMode || 'hybrid' }}</span>
      </div>
    </div>

    <div class="search-result-list" v-if="items.length">
      <SearchResultCard
        v-for="(item, index) in items"
        :key="item.drawing_id"
        :item="item"
        :index="index"
        @open-preview="emit('openPreview', item)"
      />
    </div>
  </section>
</template>
```

- [ ] **Step 5: 在 `SearchView.vue` 接线新的结果头 props**

```vue
<script setup lang="ts">
const { loading, items, total, degraded, degradedReason, lastQuery, retrievalMode, submitSearch } = useSearch()
</script>

<template>
  <SearchResultList
    :items="items"
    :total="total"
    :query="lastQuery"
    :retrieval-mode="retrievalMode"
    @open-preview="openPreview"
  />
</template>
```

- [ ] **Step 6: 运行视图测试，确认结果头改造通过**

Run:

```bash
pnpm vitest run src/views/__tests__/SearchView.test.ts
```

Expected:

```text
PASS src/views/__tests__/SearchView.test.ts
```

- [ ] **Step 7: 提交本任务改动**

```bash
git add web/src/views/SearchView.vue web/src/components/search/SearchResultList.vue web/src/composables/useSearch.ts web/src/views/__tests__/SearchView.test.ts
git commit -m "feat: reshape search results header"
```

### Task 2: 将结果卡重构为搜索结果流

**Files:**
- Modify: `d:\project\electronic_recognition\web\src\components\search\SearchResultCard.vue`
- Create: `d:\project\electronic_recognition\web\src\components\search\__tests__\SearchResultCard.test.ts`

- [ ] **Step 1: 先写卡片组件测试，约束新的信息层级和按钮语义**

```ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SearchResultCard from '../SearchResultCard.vue'

const item = {
  drawing_id: 'drawing-1',
  result_id: 'result-1',
  filename: 'demo.pdf',
  drawing_number: 'A17387_1706',
  drawing_title: '风机控制图',
  revision: 'B',
  project_name: 'Project',
  system_name: 'System',
  score: 0.88,
  matched_pages: [1, 3],
  matched_components: ['KM1'],
  matched_combinations: ['电动机启动与保护'],
  matched_chunk_types: ['drawing'],
  snippet: '第 3 页出现热继保护相关描述',
  match_sources: ['bm25'],
  preview_url: '/results/result-1#page-1',
  source_hash: '',
  collapsed_versions: 0,
  history_versions: [],
  debug: {},
}

describe('SearchResultCard', () => {
  it('renders search-style hierarchy and emits open-preview', async () => {
    const wrapper = mount(SearchResultCard, {
      props: { item, index: 0 },
    })

    expect(wrapper.text()).toContain('1')
    expect(wrapper.text()).toContain('相关度')
    expect(wrapper.text()).toContain('命中理由')
    expect(wrapper.text()).toContain('打开图纸')
    expect(wrapper.text()).not.toContain('查看结果')

    await wrapper.find('[data-action="open-preview"]').trigger('click')
    expect(wrapper.emitted('open-preview')).toHaveLength(1)
  })
})
```

- [ ] **Step 2: 运行组件测试，确认旧卡片失败**

Run:

```bash
pnpm vitest run src/components/search/__tests__/SearchResultCard.test.ts
```

Expected:

```text
FAIL
Unable to find [data-action="open-preview"]
Expected text not to contain "查看结果"
```

- [ ] **Step 3: 用最小模板重写 `SearchResultCard.vue` 的结构**

```vue
<script setup lang="ts">
import type { SearchResultItem } from '../../types/search'

const props = defineProps<{
  item: SearchResultItem
  index: number
}>()

const emit = defineEmits<{
  openPreview: []
}>()

function fmtScore(v: number) {
  return Number.isFinite(v) ? v.toFixed(3) : '--'
}

function hitReason(item: SearchResultItem) {
  const parts: string[] = []
  if (item.matched_components?.length) parts.push(`精确命中 ${item.matched_components.slice(0, 2).join(' / ')}`)
  if (item.matched_combinations?.length) parts.push(`命中 ${item.matched_combinations[0]}`)
  if (item.match_sources?.includes('dense')) parts.push('包含语义命中')
  return parts.join('，') || '命中摘要与页码信息'
}
</script>

<template>
  <article class="search-result-item search-result-item--stream">
    <div class="search-result-main">
      <header class="search-result-head">
        <span class="result-rank">{{ index + 1 }}</span>
        <div class="result-head-copy">
          <h3>{{ item.drawing_title || item.filename || item.result_id }}</h3>
          <p>{{ [item.drawing_number, item.revision && `修订 ${item.revision}`, item.project_name || item.system_name].filter(Boolean).join(' · ') }}</p>
        </div>
        <strong class="result-score">相关度 {{ fmtScore(item.score) }}</strong>
      </header>

      <p class="result-snippet">{{ item.snippet || '暂无命中摘要' }}</p>
      <div class="result-why"><b>命中理由</b><span>{{ hitReason(item) }}</span></div>

      <div class="search-tags">
        <span v-for="page in item.matched_pages.slice(0, 3)" :key="page" class="search-tag blue">命中页 {{ page }}</span>
        <span v-for="component in item.matched_components.slice(0, 2)" :key="component" class="search-tag blue">{{ component }}</span>
        <span v-for="combo in item.matched_combinations.slice(0, 1)" :key="combo" class="search-tag green">{{ combo }}</span>
      </div>

      <div class="search-result-meta">
        <span>命中证据 {{ item.matched_pages.length || 0 }} 处</span>
        <span v-if="item.collapsed_versions > 0">已折叠 {{ item.collapsed_versions }} 个历史版本</span>
      </div>
    </div>

    <aside class="search-result-actions">
      <button type="button" class="result-action result-action--primary" data-action="open-preview" @click="emit('openPreview')">打开图纸</button>
      <button type="button" class="result-action">定位命中页</button>
      <button type="button" class="result-action">展开命中</button>
    </aside>
  </article>
</template>
```

- [ ] **Step 4: 运行组件测试，确认新的层级通过**

Run:

```bash
pnpm vitest run src/components/search/__tests__/SearchResultCard.test.ts
```

Expected:

```text
PASS src/components/search/__tests__/SearchResultCard.test.ts
```

- [ ] **Step 5: 提交本任务改动**

```bash
git add web/src/components/search/SearchResultCard.vue web/src/components/search/__tests__/SearchResultCard.test.ts
git commit -m "feat: redesign search result card as result stream"
```

### Task 3: 新增悬浮大预览层并将主动作改为“打开图纸”

**Files:**
- Create: `d:\project\electronic_recognition\web\src\components\search\SearchPreviewModal.vue`
- Create: `d:\project\electronic_recognition\web\src\components\search\__tests__\SearchPreviewModal.test.ts`
- Modify: `d:\project\electronic_recognition\web\src\views\SearchView.vue`
- Modify: `d:\project\electronic_recognition\web\src\views\__tests__\SearchView.test.ts`

- [ ] **Step 1: 写预览层组件测试，覆盖打开、关闭和页码回退**

```ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SearchPreviewModal from '../SearchPreviewModal.vue'

const item = {
  drawing_id: 'drawing-1',
  result_id: 'result-1',
  filename: 'demo.pdf',
  drawing_number: 'A17387_1706',
  drawing_title: '风机控制图',
  revision: 'B',
  project_name: 'Project',
  system_name: 'System',
  score: 0.88,
  matched_pages: [1, 3],
  matched_components: [],
  matched_combinations: [],
  matched_chunk_types: [],
  snippet: 'snippet',
  match_sources: [],
  preview_url: '/results/result-1#page-1',
  source_hash: '',
  collapsed_versions: 0,
  history_versions: [],
  debug: {},
}

describe('SearchPreviewModal', () => {
  it('renders matched page navigation and emits close', async () => {
    const wrapper = mount(SearchPreviewModal, {
      props: { open: true, item },
    })

    expect(wrapper.text()).toContain('打开图纸预览')
    expect(wrapper.text()).toContain('第 1 页')
    expect(wrapper.text()).toContain('第 3 页')

    await wrapper.find('[data-action="close-preview"]').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })
})
```

- [ ] **Step 2: 运行新测试，确认组件尚不存在而失败**

Run:

```bash
pnpm vitest run src/components/search/__tests__/SearchPreviewModal.test.ts
```

Expected:

```text
FAIL
Cannot find module '../SearchPreviewModal.vue'
```

- [ ] **Step 3: 创建 `SearchPreviewModal.vue`，实现最小可用预览层**

```vue
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { SearchResultItem } from '../../types/search'

const props = defineProps<{
  open: boolean
  item: SearchResultItem | null
}>()

const emit = defineEmits<{
  close: []
}>()

const currentPage = ref<number | null>(null)

const pages = computed(() => props.item?.matched_pages ?? [])

watch(
  () => [props.open, props.item],
  () => {
    currentPage.value = pages.value[0] ?? null
  },
  { immediate: true },
)

const frameUrl = computed(() => {
  if (!props.item?.preview_url) return ''
  if (currentPage.value == null) return props.item.preview_url.split('#')[0]
  return `/results/${props.item.result_id}#page-${currentPage.value}`
})
</script>

<template>
  <teleport to="body">
    <div v-if="open && item" class="search-preview-modal" role="dialog" aria-modal="true" aria-label="打开图纸预览">
      <div class="search-preview-backdrop" @click="emit('close')" />
      <section class="search-preview-panel">
        <header class="search-preview-header">
          <div>
            <strong>打开图纸预览</strong>
            <p>{{ item.drawing_title || item.filename }} · {{ item.drawing_number || '未标注图号' }}</p>
          </div>
          <button type="button" data-action="close-preview" @click="emit('close')">关闭</button>
        </header>

        <div class="search-preview-body">
          <aside class="search-preview-nav">
            <button
              v-for="page in pages"
              :key="page"
              type="button"
              class="search-preview-page"
              :class="{ active: page === currentPage }"
              @click="currentPage = page"
            >
              第 {{ page }} 页
            </button>
            <p v-if="!pages.length">未定位具体页码，默认展示首页</p>
          </aside>

          <div class="search-preview-frame">
            <iframe :src="frameUrl" :title="item.drawing_title || item.filename" />
          </div>
        </div>
      </section>
    </div>
  </teleport>
</template>
```

- [ ] **Step 4: 在 `SearchView.vue` 中接入选中结果与预览开关**

```vue
<script setup lang="ts">
import { ref } from 'vue'
import type { SearchResultItem } from '../types/search'
import SearchPreviewModal from '../components/search/SearchPreviewModal.vue'

const previewOpen = ref(false)
const previewItem = ref<SearchResultItem | null>(null)

function openPreview(item: SearchResultItem) {
  previewItem.value = item
  previewOpen.value = true
}

function closePreview() {
  previewOpen.value = false
}
</script>

<template>
  <SearchResultList
    :items="items"
    :total="total"
    :query="lastQuery"
    :retrieval-mode="retrievalMode"
    @open-preview="openPreview"
  />

  <SearchPreviewModal
    :open="previewOpen"
    :item="previewItem"
    @close="closePreview"
  />
</template>
```

- [ ] **Step 5: 更新视图测试，断言“打开图纸”会打开预览层**

```ts
it('opens drawing preview modal from result action', async () => {
  const router = createTestRouter()
  await router.push('/search')
  await router.isReady()

  const wrapper = mount(SearchView, {
    global: { plugins: [router] },
    attachTo: document.body,
  })

  await flushPromises()
  await wrapper.find('input[type="search"]').setValue('thermal overload fan')
  await wrapper.find('form.search-form').trigger('submit')
  await flushPromises()

  await wrapper.find('[data-action="open-preview"]').trigger('click')

  expect(document.body.textContent).toContain('打开图纸预览')
  expect(document.body.textContent).toContain('第 1 页')
})
```

- [ ] **Step 6: 运行集成测试与预览层测试**

Run:

```bash
pnpm vitest run src/components/search/__tests__/SearchPreviewModal.test.ts src/views/__tests__/SearchView.test.ts
```

Expected:

```text
PASS src/components/search/__tests__/SearchPreviewModal.test.ts
PASS src/views/__tests__/SearchView.test.ts
```

- [ ] **Step 7: 提交本任务改动**

```bash
git add web/src/components/search/SearchPreviewModal.vue web/src/components/search/__tests__/SearchPreviewModal.test.ts web/src/views/SearchView.vue web/src/views/__tests__/SearchView.test.ts
git commit -m "feat: add drawing preview modal for search results"
```

### Task 4: 收口样式、替换旧文案并完成回归验证

**Files:**
- Modify: `d:\project\electronic_recognition\web\src\app\styles\search.css`
- Modify: `d:\project\electronic_recognition\web\src\components\search\SearchResultList.vue`
- Modify: `d:\project\electronic_recognition\web\src\components\search\SearchResultCard.vue`
- Test: `d:\project\electronic_recognition\web\src\views\__tests__\SearchView.test.ts`

- [ ] **Step 1: 写失败测试，覆盖旧文案被移除**

```ts
it('replaces legacy result action copy and shell labels', async () => {
  const router = createTestRouter()
  await router.push('/search')
  await router.isReady()

  const wrapper = mount(SearchView, {
    global: { plugins: [router] },
  })

  await flushPromises()
  await wrapper.find('input[type="search"]').setValue('thermal overload fan')
  await wrapper.find('form.search-form').trigger('submit')
  await flushPromises()

  expect(wrapper.text()).toContain('打开图纸')
  expect(wrapper.text()).toContain('命中理由')
  expect(wrapper.text()).not.toContain('查看结果')
  expect(wrapper.text()).not.toContain('目标区域')
})
```

- [ ] **Step 2: 运行测试，确认旧文案尚未完全清除时失败**

Run:

```bash
pnpm vitest run src/views/__tests__/SearchView.test.ts -t "replaces legacy result action copy and shell labels"
```

Expected:

```text
FAIL
Found legacy copy like "查看结果" or "目标区域"
```

- [ ] **Step 3: 在 `search.css` 中实现新的结果流与预览层样式**

```css
.search-results-summary {
  display: grid;
  gap: 10px;
  padding: 14px 16px;
  border: 1px solid #d7e0e8;
  border-radius: 16px;
  background: rgba(255,255,255,.92);
}

.search-result-item--stream {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 148px;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: #fff;
}

.result-rank {
  width: 32px;
  height: 32px;
  border-radius: 10px;
  background: #eff3f8;
  display: grid;
  place-items: center;
  font-weight: 800;
}

.result-score {
  min-width: 88px;
  padding: 8px 10px;
  border-radius: 999px;
  color: #0f6c59;
  background: #eaf7f2;
}

.result-why {
  margin-top: 12px;
  padding: 10px 12px;
  border-left: 3px solid #cfe0ff;
  border-radius: 12px;
  background: #f7faff;
}

.search-result-actions {
  padding: 14px 12px;
  border-left: 1px solid #edf2f7;
  display: grid;
  gap: 10px;
  background: #fbfcfe;
}

.search-preview-modal {
  position: fixed;
  inset: 0;
  z-index: 80;
}

.search-preview-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(14, 24, 37, 0.54);
}

.search-preview-panel {
  position: relative;
  width: min(1200px, calc(100vw - 48px));
  height: min(86vh, 920px);
  margin: 5vh auto 0;
  border-radius: 22px;
  background: #fff;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
}
```

- [ ] **Step 4: 运行完整搜索页相关测试**

Run:

```bash
pnpm vitest run src/views/__tests__/SearchView.test.ts src/components/search/__tests__/SearchResultCard.test.ts src/components/search/__tests__/SearchPreviewModal.test.ts
```

Expected:

```text
PASS 3 test files
```

- [ ] **Step 5: 运行类型检查，确认模板事件和 props 无误**

Run:

```bash
pnpm vue-tsc --noEmit
```

Expected:

```text
Done in ...
```

- [ ] **Step 6: 提交本任务改动**

```bash
git add web/src/app/styles/search.css web/src/components/search/SearchResultList.vue web/src/components/search/SearchResultCard.vue web/src/views/__tests__/SearchView.test.ts
git commit -m "feat: polish search results list redesign"
```

## Self-Review Checklist

- 规格覆盖：
  - 查询结果头：Task 1
  - 搜索结果流卡片：Task 2
  - 打开图纸 + 悬浮预览层：Task 3
  - 文案替换与样式收口：Task 4
- 占位检查：
  - 计划中未使用 `TODO`、`TBD`、`类似 Task N` 等占位语句
- 类型一致性：
  - 统一使用 `openPreview` / `open-preview`
  - 统一使用 `previewOpen`、`previewItem`
  - 主按钮文案统一为 `打开图纸`
