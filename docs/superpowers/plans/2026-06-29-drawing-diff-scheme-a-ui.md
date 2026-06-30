# 图纸比对（方案A样式）UI落地 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `web/src/views/DrawingDiffView.vue` 落地为方案A的“并排联动 + 差异红框叠加 + 右侧清单”UI，并对总览态（复位 8%）和核对态（点击清单放大 60%）的标注框样式/交互进行实现。

**Architecture:** 保留现有 compare API 与结果数据结构；新增 diff 专用组件实现并排视图与差异清单；通过 `artifacts.all_regions_url` 拉取页面宽高等元信息，拼装 old/new 渲染页 URL，并用 bbox 叠加层渲染差异红框。联动平移/缩放在前端以共享 world transform 实现。

**Tech Stack:** Vue 3, Vite, TypeScript, CSS, Vue Test Utils, Vitest

---

## 文件结构与职责

- Modify: `web/src/views/DrawingDiffView.vue`
  - 页面壳层：顶部状态、左侧输入、中心 viewer、右侧清单
- Create: `web/src/components/diff/DiffSideBySideViewer.vue`
  - 并排 viewport、联动平移/缩放、复位 8%、点击差异聚焦 60%、差异红框叠加渲染
- Create: `web/src/components/diff/DiffItemsPanel.vue`
  - 右侧差异清单：搜索/过滤/点击选中（发出事件给 viewer）
- Modify: `web/src/app/styles/diff.css`
  - 方案A暗色视觉：三栏布局、右栏收窄、红框标注（总览/核对两态）
- Modify: `web/src/types/diff.ts`
  - 增加 `DiffAllRegionsPage` 等类型（用于解析 all_regions.json）
- Modify: `web/src/views/__tests__/DrawingDiffView.test.ts`
  - 更新断言以适配新布局；补充“复位→点击条目缩放至 60%”的交互测试（尽量用 data-testid）

---

### Task 1: 为 diff 引入 all_regions 类型与 URL 拼装工具

**Files:**
- Modify: `web/src/types/diff.ts`
- Modify: `web/src/views/DrawingDiffView.vue`

- [ ] **Step 1: 扩展类型**

```ts
export interface DiffAllRegionsRegion {
  region_id: number
  bbox_px: number[]
  old_crop?: string
  new_crop?: string
  old_text?: string
  new_text?: string
  change_type?: string
}

export interface DiffAllRegionsPage {
  page: number
  offset_px: number[]
  width_px: number
  height_px: number
  regions: DiffAllRegionsRegion[]
}
```

- [ ] **Step 2: 在 view 中新增 all_regions 拉取逻辑**
  - 从 `result.data.artifacts.all_regions_url` fetch JSON
  - 缓存在 `allRegionsPages`，提供给 viewer 用于 page width/height 与 bbox 渲染

- [ ] **Step 3: 提交**

```bash
git add web/src/types/diff.ts web/src/views/DrawingDiffView.vue
git commit -m "feat(diff): add all-regions typing and load regions metadata"
```

---

### Task 2: 落地 DiffSideBySideViewer（并排联动 + 复位/聚焦规则）

**Files:**
- Create: `web/src/components/diff/DiffSideBySideViewer.vue`

- [ ] **Step 1: 新增组件骨架（props / emits）**

```vue
<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import type { DiffItem, DiffAllRegionsPage } from '../../types/diff'

const props = defineProps<{
  jobId: string | null
  page: number
  pageCount: number
  diffItems: DiffItem[]
  allRegionsPages: DiffAllRegionsPage[]
  activeDiffId: string | null
  overlayEnabled: boolean
  dimOthers: boolean
  syncEnabled: boolean
}>()

const emit = defineEmits<{
  (e: 'update:page', value: number): void
  (e: 'select', id: string): void
  (e: 'requestPrev'): void
  (e: 'requestNext'): void
}>()
</script>
```

- [ ] **Step 2: 拼装 old/new 渲染页 URL**

```ts
function pad3(n: number) {
  return String(n).padStart(3, '0')
}
function pageImageUrl(kind: 'old' | 'new', jobId: string, page: number) {
  return `/api/diff/files/${jobId}/work/rendered/${kind}_page_${pad3(page)}.png`
}
```

- [ ] **Step 3: 实现 world transform 与事件**
  - wheel 缩放、pointer drag 平移
  - 初始：fit-to-view（图片加载后）
  - 复位按钮/快捷键 0：进入总览态 scale=0.08 并居中
  - 从总览态点击清单项/上一处下一处：focus 时 scale=0.6 并居中到 bbox 中心

- [ ] **Step 4: 实现差异红框叠加层**
  - 使用 bbox_px 相对 naturalWidth/naturalHeight 转换成百分比定位
  - 样式规则：
    - 总览态（scale<=0.12）：正红色、无阴影、无填充、厚度更温和（invOverview=inv*0.62）
    - 核对态：保持红框可见但不抢占内容
  - 总览态禁止 dim；核对态允许 dim

- [ ] **Step 5: 提交**

```bash
git add web/src/components/diff/DiffSideBySideViewer.vue
git commit -m "feat(diff): add scheme-a side-by-side viewer with overlay and zoom rules"
```

---

### Task 3: 落地 DiffItemsPanel（搜索/过滤/点击选中）

**Files:**
- Create: `web/src/components/diff/DiffItemsPanel.vue`

- [ ] **Step 1: 实现面板与筛选**
  - 默认显示当前页 items（可加“全部页”开关）
  - 支持搜索（id/text/page/type）
  - 支持类型过滤（text_changed/visual_change/graphic_or_text）
  - 点击发出 `select` 事件

- [ ] **Step 2: 提交**

```bash
git add web/src/components/diff/DiffItemsPanel.vue
git commit -m "feat(diff): add scheme-a diff items panel with filters"
```

---

### Task 4: 重写 DrawingDiffView 页面布局并接线

**Files:**
- Modify: `web/src/views/DrawingDiffView.vue`
- Modify: `web/src/app/styles/diff.css`

- [ ] **Step 1: 页面布局改为三栏**
  - 左：上传/参数
  - 中：`DiffSideBySideViewer`
  - 右：`DiffItemsPanel`
  - 使用 data-testid 保证可测性（不加注释）

- [ ] **Step 2: 接线状态**
  - `activeDiffId` 由 view 管理
  - 上一处/下一处按钮：在 view 中基于 visible items 计算 index
  - viewer 的 `select` 回写 `activeDiffId`

- [ ] **Step 3: diff.css 落地方案A视觉**
  - 暗色三栏、右栏收窄、viewer 内部 padding/border
  - 红框样式使用与 mockup 一致的关键规则（总览态更温和厚度）

- [ ] **Step 4: 提交**

```bash
git add web/src/views/DrawingDiffView.vue web/src/app/styles/diff.css
git commit -m "feat(diff): apply scheme-a layout and styling to drawing diff view"
```

---

### Task 5: 更新测试并验证

**Files:**
- Modify: `web/src/views/__tests__/DrawingDiffView.test.ts`

- [ ] **Step 1: 更新断言以适配新结构**
  - 仍确保存在：标题、上传 input、清单区域
  - 增加：渲染 viewer 容器（data-testid）

- [ ] **Step 2: 补充“复位→点击条目触发 60%”测试**
  - 通过触发 reset 按钮，然后点击清单 item
  - 断言：viewer 的缩放 pill 或内部状态呈现为 60%（建议用 data-testid 输出当前 scale 文本）

- [ ] **Step 3: 运行测试**

Run: `pnpm -C web vitest run src/views/__tests__/DrawingDiffView.test.ts`
Expected: PASS

- [ ] **Step 4: 类型检查**

Run: `pnpm -C web vue-tsc --noEmit`
Expected: 0 errors

- [ ] **Step 5: 提交**

```bash
git add web/src/views/__tests__/DrawingDiffView.test.ts
git commit -m "test(diff): update drawing diff view tests for scheme-a UI"
```

---

## Self-Review

- **Spec coverage:** 覆盖三栏 UI、并排联动、复位/聚焦缩放规则、总览红框样式与清单交互。
- **Placeholder scan:** 无 TODO/TBD；每 task 给出文件与可执行命令。
- **Type consistency:** all_regions 的 page/region 字段与后端 `all_regions.json` 对齐；diff_items 继续使用现有类型。

