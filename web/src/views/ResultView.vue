<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import ResultTabs from '../components/workbench/ResultTabs.vue'
import { getResult, getResultError, getResultManifest, getResultSteps } from '../api/results'
import type { ResultDetail, ResultError, ResultManifest, ResultSteps } from '../types/results'

const route = useRoute()

const loading = ref(true)
const error = ref('')
const result = ref<ResultDetail | null>(null)
const steps = ref<ResultSteps | null>(null)
const manifest = ref<ResultManifest | null>(null)
const resultError = ref<ResultError | null>(null)
const activeTab = ref('components')
const observedRouteResultId = ref('')
let pollTimer: ReturnType<typeof setTimeout> | null = null
let activeRequestId = ''
let loadSequence = 0

const resultId = computed(() => String(route.params.resultId || ''))
const statusText = computed(() => {
  const status = result.value?.status || ''
  if (status === 'complete') return '已完成'
  if (status === 'failed') return '已失败'
  if (status) return '处理中'
  return '--'
})

const summaryItems = computed(() => [
  { label: '结果 ID', value: result.value?.result_id || resultId.value || '--' },
  { label: '文档', value: result.value?.document || '--' },
  { label: '状态', value: statusText.value },
  { label: '元件数', value: String(result.value?.detected_components?.length || 0) },
  { label: '组合数', value: String(result.value?.detected_combinations?.length || 0) },
  { label: '预览页数', value: String(result.value?.preview_pages?.length || 0) },
])

const warnings = computed(() => result.value?.warnings || [])
const stepEntries = computed(() => Object.entries(steps.value?.steps || {}))
const manifestEntries = computed(() => {
  if (!manifest.value) return []
  return [
    { label: 'updated_at', value: manifest.value.updated_at || '--' },
    { label: 'created_at', value: manifest.value.created_at || '--' },
    { label: '状态', value: manifest.value.status || '--' },
    { label: '索引状态', value: manifest.value.index_status || '--' },
  ]
})

function clearPollTimer() {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
}

async function loadResult() {
  if (!resultId.value || (loading.value && activeRequestId === resultId.value)) {
    return
  }
  const currentResultId = resultId.value
  const requestToken = ++loadSequence
  clearPollTimer()
  if (activeRequestId !== currentResultId) {
    steps.value = null
    manifest.value = null
    resultError.value = null
  }
  activeRequestId = currentResultId
  loading.value = true
  error.value = ''
  try {
    const nextResult = await getResult(currentResultId)
    if (requestToken !== loadSequence || resultId.value !== currentResultId) {
      return
    }
    result.value = nextResult
    if (nextResult.status !== 'complete' && nextResult.status !== 'failed') {
      pollTimer = setTimeout(() => {
        if (resultId.value === currentResultId) {
          void loadResult()
        }
      }, 2000)
    } else {
      await loadSupplementaryData(currentResultId, nextResult.status, requestToken)
    }
  } catch (err) {
    if (requestToken !== loadSequence || resultId.value !== currentResultId) {
      return
    }
    error.value = err instanceof Error ? err.message : '结果加载失败'
  } finally {
    if (requestToken === loadSequence) {
      activeRequestId = ''
      loading.value = false
    }
  }
}

async function loadSupplementaryData(currentResultId: string, currentStatus: string, requestToken: number) {
  const [stepsResult, manifestResult, errorResult] = await Promise.allSettled([
    getResultSteps(currentResultId),
    getResultManifest(currentResultId),
    currentStatus === 'failed'
      ? getResultError(currentResultId)
      : Promise.reject(new Error('skip-error')),
  ])

  if (requestToken !== loadSequence || resultId.value !== currentResultId) {
    return
  }
  steps.value = stepsResult.status === 'fulfilled' ? stepsResult.value : null
  manifest.value = manifestResult.status === 'fulfilled' ? manifestResult.value : null
  resultError.value = errorResult.status === 'fulfilled' ? errorResult.value : null
}

watch(resultId, async (next, previous) => {
  if (!next || next === previous) return
  if (observedRouteResultId.value === next) return
  if (activeRequestId === next || result.value?.result_id === next) return
  observedRouteResultId.value = next
  activeTab.value = 'components'
  result.value = null
  await loadResult()
}, { immediate: true })

onBeforeUnmount(() => {
  clearPollTimer()
})
</script>

<template>
  <header class="app-header app-header--result">
    <div>
      <p>Result</p>
      <h1>识别结果</h1>
    </div>
    <div class="header-actions">
      <RouterLink class="knowledge-entry" to="/workbench">识别工作台</RouterLink>
      <RouterLink class="knowledge-entry" to="/search">图纸检索</RouterLink>
      <RouterLink class="knowledge-entry" to="/drawing-diff">图纸比对</RouterLink>
      <RouterLink class="knowledge-entry" to="/knowledge">知识库管理</RouterLink>
    </div>
  </header>

  <main class="result-panel">
    <div v-if="loading" class="loading-state">
      <div class="scanner"><span></span></div>
      <h3>加载中</h3>
      <p>正在恢复识别结果与预览数据。</p>
    </div>

    <div v-else-if="error" class="empty-state">
      <div class="drawing-placeholder">!</div>
      <h3>结果加载失败</h3>
      <p>{{ error }}</p>
    </div>

    <template v-else-if="result">
      <section class="result-heading">
        <div class="section-heading">
          <p>RESULT</p>
          <h2>{{ result.document || result.result_id }}</h2>
        </div>
      </section>

      <section class="summary-grid summary-grid--compact" aria-label="结果摘要">
        <article v-for="item in summaryItems" :key="item.label">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </article>
      </section>

      <section v-if="warnings.length" class="form-section">
        <div class="section-heading">
          <p>WARNINGS</p>
          <h2>识别提示</h2>
        </div>
        <ul class="result-metadata-list">
          <li v-for="warning in warnings" :key="warning">{{ warning }}</li>
        </ul>
      </section>

      <section v-if="manifestEntries.length" class="form-section">
        <div class="section-heading">
          <p>MANIFEST</p>
          <h2>结果清单</h2>
        </div>
        <div class="summary-grid result-summary-grid">
          <article v-for="item in manifestEntries" :key="item.label">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </article>
        </div>
      </section>

      <section v-if="stepEntries.length" class="form-section">
        <div class="section-heading">
          <p>PIPELINE</p>
          <h2>Pipeline 步骤</h2>
        </div>
        <div class="result-metadata-grid">
          <article v-for="[name, payload] in stepEntries" :key="name">
            <span>{{ name }}</span>
            <strong>{{ Array.isArray(payload) ? payload.length : typeof payload === 'object' ? 'object' : String(payload ?? '--') }}</strong>
          </article>
        </div>
      </section>

      <section v-if="resultError?.error?.message" class="form-section">
        <div class="section-heading">
          <p>ERROR</p>
          <h2>失败详情</h2>
        </div>
        <p class="message error">{{ resultError.error.message }}</p>
      </section>

      <ResultTabs
        :components="result.detected_components || []"
        :combinations="result.detected_combinations || []"
        :previewPages="result.preview_pages || []"
        :componentTable="result.component_table"
        :controlSignalConfiguration="result.control_signal_configuration"
        :titleBlock="result.title_block"
        :activeTab="activeTab"
        @update:activeTab="activeTab = $event"
      />
    </template>
  </main>
</template>
