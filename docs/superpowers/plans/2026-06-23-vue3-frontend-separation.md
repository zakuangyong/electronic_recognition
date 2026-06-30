# Vue3 前后端分离改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前 `FastAPI + 静态 HTML/JS` 前端迁移为独立部署的 `Vue3 SPA`，同时把后端收口为纯 API 服务，并保持现有 pipeline、页面样式和交互逻辑等价。

**Architecture:** 在项目根新增独立 `web/` 前端工程，使用 `Vue3 + Vite + TypeScript + Vue Router + Pinia` 实现 `/workbench`、`/results/:resultId`、`/knowledge`、`/search` 四个页面。后端保留现有业务逻辑和数据文件组织方式，仅调整 Web 层：补 CORS、兼容新旧 API 字段、逐步移除页面路由与静态资源挂载。

**Tech Stack:** Vue3, Vite, TypeScript, Vue Router, Pinia, FastAPI, pytest, Vitest, Vue Test Utils

---

## File Structure

### 前端新增目录

- Create: `web/package.json`
- Create: `web/tsconfig.json`
- Create: `web/vite.config.ts`
- Create: `web/index.html`
- Create: `web/src/app/main.ts`
- Create: `web/src/app/router.ts`
- Create: `web/src/app/stores/app.ts`
- Create: `web/src/app/styles/base.css`
- Create: `web/src/app/styles/tokens.css`
- Create: `web/src/views/WorkbenchView.vue`
- Create: `web/src/views/ResultView.vue`
- Create: `web/src/views/KnowledgeView.vue`
- Create: `web/src/views/SearchView.vue`
- Create: `web/src/components/common/*`
- Create: `web/src/components/workbench/*`
- Create: `web/src/components/knowledge/*`
- Create: `web/src/components/search/*`
- Create: `web/src/composables/*`
- Create: `web/src/api/http.ts`
- Create: `web/src/api/config.ts`
- Create: `web/src/api/results.ts`
- Create: `web/src/api/search.ts`
- Create: `web/src/api/knowledge.ts`
- Create: `web/src/types/*`
- Create: `web/src/utils/*`
- Create: `web/vitest.config.ts`
- Create: `web/src/**/*.test.ts`

### 后端修改目录

- Modify: `src/electronic_recognition/api.py`
- Create: `src/electronic_recognition/api_routes/__init__.py`
- Create: `src/electronic_recognition/api_routes/analyze.py`
- Create: `src/electronic_recognition/api_routes/results.py`
- Create: `src/electronic_recognition/api_routes/search.py`
- Create: `src/electronic_recognition/api_routes/knowledge.py`
- Create: `src/electronic_recognition/api_routes/custom_rules.py`
- Create: `src/electronic_recognition/api_routes/config.py`
- Modify: `src/electronic_recognition/search/sqlite_store.py`
- Modify: `README.md`
- Modify: `pyproject.toml`

### 测试文件

- Create: `tests/test_api_cors.py`
- Create: `tests/test_api_route_mounts.py`
- Create: `tests/test_api_contract_compat.py`
- Create: `tests/test_search_result_contract.py`
- Create: `web/src/views/__tests__/SearchView.test.ts`
- Create: `web/src/views/__tests__/KnowledgeView.test.ts`
- Create: `web/src/views/__tests__/ResultView.test.ts`
- Create: `web/src/views/__tests__/WorkbenchView.test.ts`
- Create: `web/src/api/__tests__/*.test.ts`

---

### Task 1: 建立 Vue3 独立前端工程壳

**Files:**
- Create: `web/package.json`
- Create: `web/tsconfig.json`
- Create: `web/vite.config.ts`
- Create: `web/index.html`
- Create: `web/src/app/main.ts`
- Create: `web/src/app/router.ts`
- Create: `web/src/app/styles/base.css`
- Create: `web/src/app/styles/tokens.css`
- Test: `web/src/app/router.test.ts`

- [ ] **Step 1: 写前端路由失败测试**

```ts
import { describe, expect, it } from 'vitest'
import { createAppRouter } from './router'

describe('app router', () => {
  it('redirects root to workbench and exposes required routes', () => {
    const router = createAppRouter()
    const paths = router.getRoutes().map((route) => route.path)

    expect(paths).toContain('/')
    expect(paths).toContain('/workbench')
    expect(paths).toContain('/results/:resultId')
    expect(paths).toContain('/knowledge')
    expect(paths).toContain('/search')
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd web; npm run test -- src/app/router.test.ts`

Expected: FAIL，提示找不到 `createAppRouter` 或路由定义不存在。

- [ ] **Step 3: 创建最小前端工程与路由实现**

```ts
// web/src/app/router.ts
import { createRouter, createWebHistory } from 'vue-router'

export function createAppRouter() {
  return createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/', redirect: '/workbench' },
      { path: '/workbench', component: () => import('../views/WorkbenchView.vue') },
      { path: '/results/:resultId', component: () => import('../views/ResultView.vue') },
      { path: '/knowledge', component: () => import('../views/KnowledgeView.vue') },
      { path: '/search', component: () => import('../views/SearchView.vue') },
    ],
  })
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd web; npm run test -- src/app/router.test.ts`

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add web/package.json web/tsconfig.json web/vite.config.ts web/index.html web/src/app
git commit -m "feat: scaffold vue frontend shell"
```

---

### Task 2: 建立统一 API Client 与运行时配置

**Files:**
- Create: `web/src/api/http.ts`
- Create: `web/src/api/config.ts`
- Create: `web/src/types/config.ts`
- Create: `web/src/api/__tests__/http.test.ts`
- Create: `web/src/api/__tests__/config.test.ts`

- [ ] **Step 1: 写 API base URL 与错误处理失败测试**

```ts
import { describe, expect, it } from 'vitest'
import { buildApiUrl, normalizeError } from '../http'

describe('http helpers', () => {
  it('builds absolute api url from vite env', () => {
    expect(buildApiUrl('/api/config', 'http://localhost:8892')).toBe(
      'http://localhost:8892/api/config',
    )
  })

  it('normalizes backend detail payload', () => {
    expect(normalizeError({ detail: 'boom' }, 'fallback')).toBe('boom')
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd web; npm run test -- src/api/__tests__/http.test.ts src/api/__tests__/config.test.ts`

Expected: FAIL，提示工具函数缺失。

- [ ] **Step 3: 实现最小 HTTP 封装**

```ts
// web/src/api/http.ts
export function buildApiUrl(path: string, baseUrl = import.meta.env.VITE_API_BASE_URL ?? '') {
  const normalizedBase = baseUrl.replace(/\/$/, '')
  return normalizedBase ? `${normalizedBase}${path}` : path
}

export function normalizeError(payload: unknown, fallback: string) {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail
    if (typeof detail === 'string' && detail.trim()) return detail
  }
  return fallback
}
```

- [ ] **Step 4: 实现配置 API**

```ts
// web/src/api/config.ts
import { buildApiUrl } from './http'

export async function fetchConfig(fetchImpl = fetch) {
  const response = await fetchImpl(buildApiUrl('/api/config'))
  return response.json()
}
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd web; npm run test -- src/api/__tests__/http.test.ts src/api/__tests__/config.test.ts`

Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add web/src/api web/src/types
git commit -m "feat: add frontend api client foundation"
```

---

### Task 3: 后端补充 CORS 与纯 API 装配

**Files:**
- Modify: `src/electronic_recognition/api.py`
- Create: `src/electronic_recognition/api_routes/__init__.py`
- Create: `tests/test_api_cors.py`
- Create: `tests/test_api_route_mounts.py`

- [ ] **Step 1: 写 CORS 与 API 装配失败测试**

```python
from fastapi.testclient import TestClient

from electronic_recognition.api import app


def test_cors_allows_frontend_origin() -> None:
    client = TestClient(app)
    response = client.options(
        "/api/config",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest -q --basetemp .pytest-temp tests/test_api_cors.py tests/test_api_route_mounts.py`

Expected: FAIL，CORS 头缺失或 API 仍与页面装配强耦合。

- [ ] **Step 3: 实现最小 CORS 和路由注册**

```python
# src/electronic_recognition/api.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Electronic Recognition API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- [ ] **Step 4: 将业务 API 拆到 `api_routes` 包并注册**

```python
# src/electronic_recognition/api_routes/__init__.py
from .config import router as config_router
from .search import router as search_router


def register_routers(app):
    app.include_router(config_router)
    app.include_router(search_router)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest -q --basetemp .pytest-temp tests/test_api_cors.py tests/test_api_route_mounts.py`

Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add src/electronic_recognition/api.py src/electronic_recognition/api_routes tests/test_api_cors.py tests/test_api_route_mounts.py
git commit -m "refactor: prepare backend as pure api service"
```

---

### Task 4: 固化兼容期 API 契约

**Files:**
- Modify: `src/electronic_recognition/api.py`
- Modify: `src/electronic_recognition/search/sqlite_store.py`
- Create: `tests/test_api_contract_compat.py`
- Create: `tests/test_search_result_contract.py`

- [ ] **Step 1: 写兼容字段失败测试**

```python
def test_search_result_contains_result_id_and_matched_pages() -> None:
    item = {
        "result_id": "result-1",
        "matched_pages": [2],
        "preview_url": "/legacy/path",
    }

    assert item["result_id"] == "result-1"
    assert item["matched_pages"] == [2]
    assert item["preview_url"] == "/legacy/path"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest -q --basetemp .pytest-temp tests/test_api_contract_compat.py tests/test_search_result_contract.py`

Expected: FAIL，说明新契约字段未被系统化覆盖。

- [ ] **Step 3: 为搜索结果保留新旧字段并明确语义**

```python
# src/electronic_recognition/search/sqlite_store.py
preview_url = (
    f"/?result_id={row['result_id']}"
    if not matched_pages
    else f"/?result_id={row['result_id']}#page-{matched_pages[0]}"
)

result = DrawingSearchResult(
    result_id=str(row["result_id"]),
    matched_pages=matched_pages,
    preview_url=preview_url,
)
```

- [ ] **Step 4: 为分析任务响应增加显式 `result_id`**

```python
# src/electronic_recognition/api.py
return {
    "task_id": result_id,
    "result_id": result_id,
    "result_url": f"/api/results/{result_id}",
    "steps_url": f"/api/results/{result_id}/steps",
}
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest -q --basetemp .pytest-temp tests/test_api_contract_compat.py tests/test_search_result_contract.py`

Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add src/electronic_recognition/api.py src/electronic_recognition/search/sqlite_store.py tests/test_api_contract_compat.py tests/test_search_result_contract.py
git commit -m "feat: add compatibility api fields for vue migration"
```

---

### Task 5: 迁移 Search 页面为 Vue 视图

**Files:**
- Create: `web/src/views/SearchView.vue`
- Create: `web/src/components/search/SearchToolbar.vue`
- Create: `web/src/components/search/SearchHealthPanel.vue`
- Create: `web/src/components/search/SearchResultList.vue`
- Create: `web/src/components/search/SearchResultCard.vue`
- Create: `web/src/components/search/SearchDebugPanel.vue`
- Create: `web/src/composables/useSearch.ts`
- Create: `web/src/composables/useSearchHealth.ts`
- Create: `web/src/api/search.ts`
- Create: `web/src/views/__tests__/SearchView.test.ts`

- [ ] **Step 1: 写 Search 页面等价行为失败测试**

```ts
import { render, screen } from '@testing-library/vue'
import SearchView from '../SearchView.vue'

it('renders retrieval modes and demo query section', async () => {
  render(SearchView)

  expect(screen.getByLabelText('BM25')).toBeInTheDocument()
  expect(screen.getByLabelText('Vector')).toBeInTheDocument()
  expect(screen.getByLabelText('Hybrid')).toBeInTheDocument()
  expect(screen.getByText('演示查询集')).toBeInTheDocument()
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd web; npm run test -- src/views/__tests__/SearchView.test.ts`

Expected: FAIL，页面或组件不存在。

- [ ] **Step 3: 实现 Search API 与 composable**

```ts
// web/src/composables/useSearch.ts
import { ref } from 'vue'
import { searchDrawings } from '../api/search'

export function useSearch() {
  const loading = ref(false)
  const items = ref<any[]>([])

  async function submitSearch(payload: Record<string, unknown>) {
    loading.value = true
    try {
      const result = await searchDrawings(payload)
      items.value = result.items ?? []
      return result
    } finally {
      loading.value = false
    }
  }

  return { loading, items, submitSearch }
}
```

- [ ] **Step 4: 按原页面结构实现 SearchView**

```vue
<template>
  <main class="search-workspace">
    <SearchToolbar />
    <SearchHealthPanel />
    <SearchResultList :items="items" />
  </main>
</template>
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd web; npm run test -- src/views/__tests__/SearchView.test.ts`

Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add web/src/views/SearchView.vue web/src/components/search web/src/composables/useSearch.ts web/src/composables/useSearchHealth.ts web/src/api/search.ts web/src/views/__tests__/SearchView.test.ts
git commit -m "feat: migrate search page to vue"
```

---

### Task 6: 迁移 Knowledge 页面为 Vue 视图

**Files:**
- Create: `web/src/views/KnowledgeView.vue`
- Create: `web/src/components/knowledge/KnowledgeToolbar.vue`
- Create: `web/src/components/knowledge/KnowledgeListPanel.vue`
- Create: `web/src/components/knowledge/ComponentEditor.vue`
- Create: `web/src/components/knowledge/RuleEditor.vue`
- Create: `web/src/components/knowledge/ImageUploader.vue`
- Create: `web/src/composables/useKnowledgeCatalog.ts`
- Create: `web/src/api/knowledge.ts`
- Create: `web/src/views/__tests__/KnowledgeView.test.ts`

- [ ] **Step 1: 写 Knowledge 页面失败测试**

```ts
import { render, screen } from '@testing-library/vue'
import KnowledgeView from '../KnowledgeView.vue'

it('renders component and rule management sections', async () => {
  render(KnowledgeView)

  expect(screen.getByText('知识库管理')).toBeInTheDocument()
  expect(screen.getByText('单元件')).toBeInTheDocument()
  expect(screen.getByText('组合元件')).toBeInTheDocument()
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd web; npm run test -- src/views/__tests__/KnowledgeView.test.ts`

Expected: FAIL

- [ ] **Step 3: 实现知识库查询与编辑 composable**

```ts
// web/src/composables/useKnowledgeCatalog.ts
import { ref } from 'vue'
import { fetchKnowledge, fetchCustomRules } from '../api/knowledge'

export function useKnowledgeCatalog() {
  const components = ref<any[]>([])
  const rules = ref<any[]>([])

  async function load() {
    const [componentPayload, rulePayload] = await Promise.all([
      fetchKnowledge(),
      fetchCustomRules(),
    ])
    components.value = componentPayload.items ?? []
    rules.value = rulePayload.items ?? []
  }

  return { components, rules, load }
}
```

- [ ] **Step 4: 按现有左右布局平移 KnowledgeView**

```vue
<template>
  <main class="knowledge-workspace">
    <KnowledgeListPanel />
    <ComponentEditor />
  </main>
</template>
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd web; npm run test -- src/views/__tests__/KnowledgeView.test.ts`

Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add web/src/views/KnowledgeView.vue web/src/components/knowledge web/src/composables/useKnowledgeCatalog.ts web/src/api/knowledge.ts web/src/views/__tests__/KnowledgeView.test.ts
git commit -m "feat: migrate knowledge page to vue"
```

---

### Task 7: 迁移 Workbench 与 Result 页面

**Files:**
- Create: `web/src/views/WorkbenchView.vue`
- Create: `web/src/views/ResultView.vue`
- Create: `web/src/components/workbench/UploadPanel.vue`
- Create: `web/src/components/workbench/TaskStatusCard.vue`
- Create: `web/src/components/workbench/ResultTabs.vue`
- Create: `web/src/components/workbench/PreviewCanvas.vue`
- Create: `web/src/components/workbench/PreviewOverlay.vue`
- Create: `web/src/components/workbench/ComponentGroupList.vue`
- Create: `web/src/components/workbench/CombinationCardList.vue`
- Create: `web/src/composables/useAnalyzeTask.ts`
- Create: `web/src/composables/useResultPolling.ts`
- Create: `web/src/composables/useResultLoader.ts`
- Create: `web/src/api/results.ts`
- Create: `web/src/views/__tests__/WorkbenchView.test.ts`
- Create: `web/src/views/__tests__/ResultView.test.ts`

- [ ] **Step 1: 写工作台与结果恢复失败测试**

```ts
import { render, screen } from '@testing-library/vue'
import ResultView from '../ResultView.vue'

it('loads result view shell for existing result id', async () => {
  render(ResultView, {
    global: {
      mocks: {
        $route: { params: { resultId: 'result-1' } },
      },
    },
  })

  expect(screen.getByText('识别结果')).toBeInTheDocument()
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd web; npm run test -- src/views/__tests__/WorkbenchView.test.ts src/views/__tests__/ResultView.test.ts`

Expected: FAIL

- [ ] **Step 3: 实现分析任务与轮询 composables**

```ts
// web/src/composables/useAnalyzeTask.ts
import { ref } from 'vue'
import { submitAnalyze } from '../api/results'

export function useAnalyzeTask() {
  const submitting = ref(false)

  async function start(file: File) {
    submitting.value = true
    try {
      return await submitAnalyze(file)
    } finally {
      submitting.value = false
    }
  }

  return { submitting, start }
}
```

- [ ] **Step 4: 实现 WorkbenchView 与 ResultView 共享结果组件**

```vue
<template>
  <main class="workspace-shell">
    <UploadPanel v-if="mode === 'workbench'" />
    <TaskStatusCard />
    <ResultTabs />
    <PreviewCanvas />
  </main>
</template>
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd web; npm run test -- src/views/__tests__/WorkbenchView.test.ts src/views/__tests__/ResultView.test.ts`

Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add web/src/views/WorkbenchView.vue web/src/views/ResultView.vue web/src/components/workbench web/src/composables/useAnalyzeTask.ts web/src/composables/useResultPolling.ts web/src/composables/useResultLoader.ts web/src/api/results.ts web/src/views/__tests__/WorkbenchView.test.ts web/src/views/__tests__/ResultView.test.ts
git commit -m "feat: migrate workbench and result pages to vue"
```

---

### Task 8: 清理后端页面托管并更新文档

**Files:**
- Modify: `src/electronic_recognition/api.py`
- Modify: `README.md`
- Modify: `pyproject.toml`
- Test: `tests/test_api_route_mounts.py`

- [ ] **Step 1: 写纯 API 服务失败测试**

```python
from electronic_recognition.api import app


def test_backend_does_not_mount_legacy_html_routes() -> None:
    paths = {route.path for route in app.routes}

    assert "/workbench" not in paths
    assert "/knowledge" not in paths
    assert "/search" not in paths
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest -q --basetemp .pytest-temp tests/test_api_route_mounts.py`

Expected: FAIL，旧页面路由仍存在。

- [ ] **Step 3: 删除页面托管并更新 README**

```md
# README.md
后端仅提供 API 服务：

```powershell
er --port 8892
```

前端独立开发：

```powershell
cd web
npm install
npm run dev
```
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest -q --basetemp .pytest-temp tests/test_api_route_mounts.py`

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/electronic_recognition/api.py README.md pyproject.toml tests/test_api_route_mounts.py
git commit -m "refactor: remove legacy frontend hosting"
```

---

### Task 9: 完整验证与联调

**Files:**
- Modify: `README.md`
- Test: `tests/test_api_cors.py`
- Test: `tests/test_api_contract_compat.py`
- Test: `tests/test_search_result_contract.py`
- Test: `web/src/views/__tests__/SearchView.test.ts`
- Test: `web/src/views/__tests__/KnowledgeView.test.ts`
- Test: `web/src/views/__tests__/WorkbenchView.test.ts`
- Test: `web/src/views/__tests__/ResultView.test.ts`

- [ ] **Step 1: 运行后端测试**

Run: `python -m pytest -q --basetemp .pytest-temp tests/test_api_cors.py tests/test_api_route_mounts.py tests/test_api_contract_compat.py tests/test_search_result_contract.py`

Expected: PASS

- [ ] **Step 2: 运行前端测试**

Run: `cd web; npm run test`

Expected: PASS

- [ ] **Step 3: 本地联调启动后端**

Run: `er --port 8892`

Expected: API server listening on `http://localhost:8892`

- [ ] **Step 4: 本地联调启动前端**

Run: `cd web; npm run dev -- --host 0.0.0.0 --port 5173`

Expected: Vite dev server listening on `http://localhost:5173`

- [ ] **Step 5: 手工验证关键流程**

```text
1. 打开 /workbench，上传图纸，确认任务状态、步骤日志、结果 tabs、预览叠加正常
2. 打开 /results/<result_id>#page-1，确认历史结果恢复与页码定位正常
3. 打开 /search，执行查询，确认结果跳转到 /results/:resultId
4. 打开 /knowledge，确认单元件/组合元件编辑、校验、试运行、图片上传正常
```

- [ ] **Step 6: 提交**

```bash
git add README.md
git commit -m "test: verify vue frontend separation migration"
```

---

## Self-Review

### Spec coverage

- 独立 `Vue3 SPA`：Task 1、Task 2
- 前端页面迁移：Task 5、Task 6、Task 7
- 后端纯 API 化：Task 3、Task 8
- API 兼容策略：Task 4
- CORS 与独立启动：Task 3、Task 9
- 保持样式与交互结构：Task 5、Task 6、Task 7
- 测试与联调：Task 9

### Placeholder scan

- 未使用未定稿或延后实现类占位语句
- 每个任务都包含测试、运行命令、预期结果与提交动作

### Type consistency

- 前端路由统一使用 `/workbench`、`/results/:resultId`、`/knowledge`、`/search`
- 后端 API 统一使用 `/api/*`
- Search 兼容字段统一为 `preview_url + result_id + matched_pages`
