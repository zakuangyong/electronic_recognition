# 图纸预览新增页签 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 WorkbenchView 与 ResultView 的图纸预览（ResultTabs）中新增「图纸标签表 / 控制-信号信息 / 图签信息」三个页签，并支持空态与 JSON 兜底。

**Architecture:** 扩展现有 `ResultTabs.vue`：新增 3 个 tab key，并通过新增 props 接收 `component_table / control_signal_configuration / title_block`。展示采用“半结构化 + JSON 展开”的降级策略。

**Tech Stack:** Vue 3 + TypeScript + Vite + Vitest + Vue Test Utils

---

## Files

**Modify**
- `web/src/components/workbench/ResultTabs.vue`
- `web/src/views/WorkbenchView.vue`
- `web/src/views/ResultView.vue`
- `web/src/components/workbench/__tests__/RecognitionDisplay.test.ts`
- `web/src/views/__tests__/ResultView.test.ts`（必要时补断言/避免回归）

---

### Task 1: 为新增页签写失败测试（RED）

**Files:**
- Modify: `web/src/components/workbench/__tests__/RecognitionDisplay.test.ts`

- [ ] **Step 1: Write failing test for new preview tabs**

```ts
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ResultTabs from '../ResultTabs.vue'

describe('result tabs extra preview panels', () => {
  it('renders extra preview tabs and shows empty states', async () => {
    const wrapper = mount(ResultTabs, {
      props: {
        components: [],
        combinations: [],
        previewPages: [],
        activeTab: 'tag-table',
        componentTable: {},
        controlSignalConfiguration: {},
        titleBlock: {},
      },
    })

    expect(wrapper.text()).toContain('图纸标签表')
    expect(wrapper.text()).toContain('控制/信号信息')
    expect(wrapper.text()).toContain('图签信息')
    expect(wrapper.text()).toContain('暂无图纸标签表')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pnpm vitest run src/components/workbench/__tests__/RecognitionDisplay.test.ts
```

Expected: FAIL（因为 `ResultTabs` 尚未渲染新增页签文案/空态）

---

### Task 2: 扩展 ResultTabs（GREEN）

**Files:**
- Modify: `web/src/components/workbench/ResultTabs.vue`

- [ ] **Step 1: Add props for meta payloads**

```ts
const props = defineProps<{
  components: ComponentData[]
  combinations: CombinationData[]
  previewPages: PreviewPage[]
  activeTab: string
  loading?: boolean
  componentTable?: unknown
  controlSignalConfiguration?: unknown
  titleBlock?: unknown
}>()
```

- [ ] **Step 2: Add new tab items**

Ensure tab keys:
- `tag-table`
- `control-signal`
- `title-block`

- [ ] **Step 3: Implement UI for each tab**

For each new tab:
- Empty state when payload is null/undefined/empty object/empty array
- “复制 JSON”按钮（try/catch 调用 `navigator.clipboard.writeText`）
- “展开/收起原始 JSON”按钮（切换显示 `<pre>{{ JSON.stringify(payload, null, 2) }}</pre>`）
- Structured rendering:
  - array -> auto table (columns from keys, limit columns)
  - object -> key-value list (`<dl>` or `<table>`)

- [ ] **Step 4: Run the same test to verify it passes**

Run:

```bash
pnpm vitest run src/components/workbench/__tests__/RecognitionDisplay.test.ts
```

Expected: PASS

---

### Task 3: Workbench 与 ResultView 接入三字段

**Files:**
- Modify: `web/src/views/WorkbenchView.vue`
- Modify: `web/src/views/ResultView.vue`
- Test: `web/src/views/__tests__/WorkbenchView.test.ts`
- Test: `web/src/views/__tests__/ResultView.test.ts`

- [ ] **Step 1: WorkbenchView 传入 props**

```vue
<ResultTabs
  ...
  :componentTable="result?.component_table"
  :controlSignalConfiguration="result?.control_signal_configuration"
  :titleBlock="result?.title_block"
/>
```

- [ ] **Step 2: ResultView 传入 props**

```vue
<ResultTabs
  ...
  :componentTable="result.component_table"
  :controlSignalConfiguration="result.control_signal_configuration"
  :titleBlock="result.title_block"
/>
```

- [ ] **Step 3: Run view tests and typecheck**

Run:

```bash
pnpm vitest run src/views/__tests__/WorkbenchView.test.ts src/views/__tests__/ResultView.test.ts
pnpm vue-tsc --noEmit
```

Expected: PASS

---

### Task 4: 回归验证

- [ ] **Step 1: Run focused tests**

```bash
pnpm vitest run
```

- [ ] **Step 2: Manual check**
- Workbench: 上传后切换新增三个页签，查看空态/JSON 展开
- ResultView: 打开 `/results/<id>` 切换新增三个页签

