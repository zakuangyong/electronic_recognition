<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import SearchPreviewModal from '../components/search/SearchPreviewModal.vue'
import SearchToolbar from '../components/search/SearchToolbar.vue'
import SearchResultList from '../components/search/SearchResultList.vue'
import { rebuildIndex } from '../api/search'
import { useSearch } from '../composables/useSearch'
import { useSearchHealth } from '../composables/useSearchHealth'
import type { SearchQuery, SearchResultItem } from '../types/search'
import { buildApiUrl } from '../api/http'

import '../app/styles/search.css'
import '../app/styles/diff.css'

type ToolbarExpose = {
  query: string
  mode: string
  rebuildMode: string
  submitSearch: () => void
  handleRebuild: () => void
}

const toolbarRef = ref<ToolbarExpose | null>(null)
const modalOpen = ref(false)
const selectedItem = ref<SearchResultItem | null>(null)
const currentPage = ref<number | null>(null)

const message = ref<{ type: 'info' | 'success' | 'error'; text: string } | null>(
  null,
)

const { loading, items, total, degraded, degradedReason, lastQuery, retrievalMode, submitSearch } =
  useSearch()
const {
  status: healthStatus,
  error: healthError,
  refresh: refreshHealth,
} = useSearchHealth()

function setMessage(type: 'info' | 'success' | 'error', text: string) {
  message.value = { type, text }
}

async function handleSearch(payload: SearchQuery) {
  message.value = null
  try {
    await submitSearch(payload)
  } catch (err) {
    setMessage('error', err instanceof Error ? err.message : '检索失败')
  }
}

async function handleRebuild(mode: string) {
  message.value = null
  try {
    await rebuildIndex({ force: true, mode })
    setMessage('success', '索引重建任务已触发')
    await refreshHealth()
  } catch (err) {
    setMessage('error', err instanceof Error ? err.message : '重建索引失败')
  }
}

function selectResult(item: SearchResultItem) {
  selectedItem.value = item
}

function openPreview(item: SearchResultItem) {
  selectedItem.value = item
  modalOpen.value = true
}

function closePreview() {
  modalOpen.value = false
}

onMounted(async () => {
  await refreshHealth()
})

watch(
  () => selectedItem.value?.matched_pages?.join(',') || selectedItem.value?.result_id || '',
  () => {
    currentPage.value = selectedItem.value?.matched_pages?.[0] ?? null
  },
  { immediate: true },
)

const healthLabel = computed(() => {
  if (healthError.value) return '连接异常'
  if (degraded.value) return '降级运行'
  return '检索就绪'
})

const isInternalPreview = computed(() => {
  const url = selectedItem.value?.preview_url
  return !url || url.startsWith('/results/') || url.startsWith('/api/results/')
})
const previewBaseUrl = computed(() => {
  if (!selectedItem.value) return ''
  if (isInternalPreview.value) {
    return buildApiUrl(`/api/results/${selectedItem.value.result_id}/preview-file`)
  }
  const previewUrl = selectedItem.value.preview_url ?? ''
  return previewUrl.split('#')[0] || previewUrl
})

function previewPageUrl(page: number): string {
  if (!selectedItem.value) return ''
  if (isInternalPreview.value) {
    return buildApiUrl(`/api/results/${selectedItem.value.result_id}/preview-page/${page}`)
  }
  return `${previewBaseUrl.value}#page-${page}`
}

const frameUrl = computed(() => {
  if (!selectedItem.value) return ''
  if (currentPage.value == null) {
    return previewBaseUrl.value
  }
  return previewPageUrl(currentPage.value)
})

const previewTitle = computed(() => selectedItem.value?.drawing_title || selectedItem.value?.filename || 'drawing preview')
const shouldScalePageImage = computed(() => isInternalPreview.value && currentPage.value != null)
</script>

<template>
  <div class="diff-a-root">
    <div class="topbar topbar--dark">
      <div>
        <h1>图纸检索</h1>
        <p>SEARCH · FILTER → LIST → PREVIEW</p>
      </div>
      <div class="chips">
        <RouterLink class="chip" to="/workbench">识别工作台</RouterLink>
        <RouterLink class="chip active" to="/search">图纸检索</RouterLink>
        <RouterLink class="chip" to="/drawing-diff">图纸比对</RouterLink>
        <RouterLink class="chip" to="/drawing-correction">图纸纠错</RouterLink>
        <RouterLink class="chip" to="/knowledge">知识库管理</RouterLink>
      </div>
    </div>

    <section class="diff-a-shell">
      <header class="diff-a-topbar">
        <div class="diff-a-meta">
          <span class="diff-a-pill">
            <span class="diff-a-dot"></span>
            <b>{{ healthLabel }}</b>
            <span>{{ toolbarRef?.mode || healthStatus?.mode || 'bm25' }}</span>
          </span>
          <span class="diff-a-pill">
            <span class="diff-a-dot"></span>
            <b>{{ total }}</b>
            <span>hits</span>
          </span>
          <span class="diff-a-pill">
            <span class="diff-a-dot"></span>
            <b>{{ lastQuery || '—' }}</b>
            <span>查询</span>
          </span>
        </div>
        <div class="diff-a-actions">
          <button class="diff-a-chip diff-a-chip--primary" type="button" @click="toolbarRef?.submitSearch()">
            开始检索
          </button>
          <button class="diff-a-chip" data-action="rebuild-index" type="button" @click="toolbarRef?.handleRebuild()">
            重建索引
          </button>
          <button class="diff-a-chip" data-capability="save-query" type="button" disabled>
            保存查询
          </button>
        </div>
      </header>

      <main class="diff-a-board" aria-label="图纸检索">
        <aside class="diff-a-panel">
          <header class="diff-a-panelHeader">
            <div class="diff-a-h">
              <b>检索条件</b>
              <span>条件 · 过滤 · 模式</span>
            </div>
            <span class="diff-a-tag">filters</span>
          </header>
          <div class="diff-a-panelBody">
            <SearchToolbar
              ref="toolbarRef"
              :loading="loading"
              @search="handleSearch"
              @rebuild="handleRebuild"
            />
            <p
              v-if="message"
              class="diff-a-msg"
              :class="message.type"
              role="status"
              aria-live="polite"
            >
              {{ message.text }}
            </p>
            <p v-if="degraded" class="diff-a-msg info" role="status" aria-live="polite">
              {{ degradedReason || '当前检索链路处于降级状态' }}
            </p>
            <div class="diff-a-note">
              点击中间某条结果会在右侧展示预览与命中摘要；右侧“放大预览”会打开弹窗。
            </div>
          </div>
        </aside>

        <section class="diff-a-panel">
          <header class="diff-a-panelHeader">
            <div class="diff-a-h">
              <b>查询结果</b>
              <span>grouped by drawing</span>
            </div>
            <span class="diff-a-tag">results</span>
          </header>
          <div class="diff-a-panelBody">
            <SearchResultList
              :items="items"
              :total="total"
              :query="lastQuery"
              :retrieval-mode="retrievalMode"
              :loading="loading"
              @select="selectResult"
              @open-preview="openPreview"
            />
          </div>
        </section>

        <aside class="diff-a-panel">
          <header class="diff-a-panelHeader">
            <div class="diff-a-h">
              <b>预览与详情</b>
              <span>selected · pages · snippet</span>
            </div>
            <span class="diff-a-tag">preview</span>
          </header>
          <div class="diff-a-panelBody">
            <template v-if="selectedItem">
              <div class="diff-a-note">
                <b>{{ selectedItem.drawing_title || selectedItem.filename }}</b>
                <div style="margin-top: 6px; color: rgba(255, 255, 255, 0.66)">
                  {{ selectedItem.drawing_number || '未标注图号' }} · {{ selectedItem.project_name || '—' }} ·
                  {{ selectedItem.revision || '—' }}
                </div>
              </div>

              <div class="diff-a-controls" style="justify-content: space-between">
                <div class="diff-a-pills">
                  <span class="diff-a-mini">{{ selectedItem.matched_pages?.length || 0 }} pages</span>
                  <span class="diff-a-mini">{{ (selectedItem.score || 0).toFixed(2) }} score</span>
                </div>
                <button class="diff-a-chip" type="button" @click="modalOpen = true">放大预览</button>
              </div>

              <div class="diff-a-controls" style="justify-content: flex-start">
                <button
                  v-for="p in (selectedItem.matched_pages || [])"
                  :key="p"
                  class="diff-a-chip"
                  type="button"
                  :disabled="loading"
                  @click="currentPage = p"
                >
                  第 {{ p }} 页
                </button>
              </div>

              <div class="diff-a-panel" style="border-radius: 16px">
                <div class="diff-a-panelHeader">
                  <div class="diff-a-h">
                    <b>图纸预览</b>
                    <span>{{ currentPage == null ? 'home' : `page ${currentPage}` }}</span>
                  </div>
                </div>
                <div class="diff-a-panelBody" style="padding: 10px">
                  <img
                    v-if="shouldScalePageImage"
                    :src="frameUrl"
                    :alt="previewTitle"
                    style="width: 100%; border-radius: 14px; border: 1px solid rgba(255, 255, 255, 0.1); background: rgba(0, 0, 0, 0.12)"
                  />
                  <iframe
                    v-else
                    :src="frameUrl"
                    :title="previewTitle"
                    style="width: 100%; height: 280px; border-radius: 14px; border: 1px solid rgba(255, 255, 255, 0.1); background: rgba(0, 0, 0, 0.12)"
                  />
                </div>
              </div>

              <div class="diff-a-note">
                <b>命中摘要</b>：{{ selectedItem.snippet || '—' }}
              </div>
            </template>
            <div v-else class="diff-a-empty diff-a-empty--small">
              <div>
                <h3>等待选择</h3>
                <p>从中间列表选择一条结果后，右侧展示预览与命中详情。</p>
              </div>
            </div>
          </div>
        </aside>
      </main>
    </section>
  </div>

  <SearchPreviewModal :open="modalOpen && Boolean(selectedItem)" :item="selectedItem" @close="closePreview" />
</template>
