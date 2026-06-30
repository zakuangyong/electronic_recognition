<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import UploadPanel from '../components/workbench/UploadPanel.vue'
import WorkbenchPreviewTabs from '../components/workbench/WorkbenchPreviewTabs.vue'
import RecognitionLogPanel from '../components/workbench/RecognitionLogPanel.vue'
import { useResultPolling } from '../composables/useResultPolling'
import type {
  AnalyzeResponse,
  CombinationData,
  ComponentData,
  LogEntry,
  PreviewPage,
} from '../types/results'
import { fetchConfig } from '../api/config'

import '../app/styles/diff.css'

const task = ref<AnalyzeResponse | null>(null)
const activeTab = ref('component-identification')
const message = ref<{ type: 'info' | 'success' | 'error'; text: string } | null>(
  null,
)
const visionModel = ref<string | null>(null)

const { result, steps, manifest, loading, startPolling } = useResultPolling()

const resultId = computed(() => result.value?.result_id || task.value?.result_id || '')
const status = computed(() => result.value?.status || steps.value?.status || task.value?.status || '')
const running = computed(() => status.value !== 'complete' && status.value !== 'failed')
const recognitionLoading = computed(() => Boolean(resultId.value && running.value && loading.value))
const statusLabel = computed(() => {
  if (!resultId.value) return '未开始'
  if (status.value === 'complete') return '已完成'
  if (status.value === 'failed') return '已失败'
  return '处理中'
})

const stepPayloads = computed<Record<string, unknown>>(() => {
  const payload = steps.value?.steps
  return payload && typeof payload === 'object' && !Array.isArray(payload)
    ? payload as Record<string, unknown>
    : {}
})

const resultIsTerminal = computed(() => result.value?.status === 'complete' || result.value?.status === 'failed')

function hasStepPayload(name: string): boolean {
  return Object.prototype.hasOwnProperty.call(stepPayloads.value, name)
}

function hasPayloadValue(payload: unknown): boolean {
  if (payload == null) return false
  if (Array.isArray(payload)) return payload.length > 0
  if (typeof payload === 'object') return Object.keys(payload as Record<string, unknown>).length > 0
  return true
}

function payloadFromProgress(name: string, resultPayload: unknown): unknown {
  const stepPayload = hasStepPayload(name) ? stepPayloads.value[name] : undefined
  if (resultIsTerminal.value) return hasPayloadValue(resultPayload) ? resultPayload : stepPayload
  return stepPayload ?? resultPayload
}

function arrayPayload<T>(name: string, resultPayload: unknown): T[] {
  const payload = payloadFromProgress(name, resultPayload)
  return Array.isArray(payload) ? payload as T[] : []
}

function objectPayload(name: string, resultPayload: unknown): Record<string, unknown> {
  const payload = payloadFromProgress(name, resultPayload)
  return payload && typeof payload === 'object' && !Array.isArray(payload)
    ? payload as Record<string, unknown>
    : {}
}

const components = computed<ComponentData[]>(() => arrayPayload<ComponentData>('detected_components', result.value?.detected_components))
const combinations = computed<CombinationData[]>(() => arrayPayload<CombinationData>('detected_combinations', result.value?.detected_combinations))
const previewPages = computed<PreviewPage[]>(() => arrayPayload<PreviewPage>('preview_pages', result.value?.preview_pages))
const warnings = computed<string[]>(() => arrayPayload<string>('warnings', result.value?.warnings))
const warningCount = computed(() => warnings.value.length)
const titleBlock = computed(() => objectPayload('title_block', result.value?.title_block))
const controlSignalConfiguration = computed(() => objectPayload(
  'control_signal_configuration',
  result.value?.control_signal_configuration,
))
const componentTable = computed(() => objectPayload('component_table', result.value?.component_table))

const logEntries = computed<LogEntry[]>(() => {
  const raw = (steps.value?.steps as Record<string, unknown> | undefined)?.recognition_log
  return Array.isArray(raw) ? (raw as LogEntry[]) : []
})

function setMessage(type: 'info' | 'success' | 'error', text: string) {
  message.value = { type, text }
}

function handleSubmitted(payload: AnalyzeResponse) {
  task.value = payload
  message.value = null
  activeTab.value = 'component-identification'
  if (payload.result_id) {
    startPolling(payload.result_id)
    setMessage('success', `任务已提交：${payload.result_id}`)
  } else {
    setMessage('error', '提交成功但未返回结果 ID')
  }
}

onMounted(async () => {
  try {
    const config = await fetchConfig()
    visionModel.value = config.model
  } catch {
    visionModel.value = null
  }
})
</script>

<template>
  <div class="diff-a-root">
    <div class="topbar topbar--dark">
      <div>
        <h1>识别工作台</h1>
        <p>WORKBENCH · PIPELINE</p>
      </div>
      <div class="chips">
        <RouterLink class="chip active" to="/workbench">识别工作台</RouterLink>
        <RouterLink class="chip" to="/search">图纸检索</RouterLink>
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
            <b>{{ statusLabel }}</b>
            <span>{{ resultId ? `result ${resultId}` : 'waiting' }}</span>
          </span>
          <span class="diff-a-pill">
            <span class="diff-a-dot"></span>
            <b>{{ previewPages.length || '--' }}</b>
            <span>pages</span>
          </span>
          <span class="diff-a-pill">
            <span class="diff-a-dot"></span>
            <b>{{ components.length }}</b>
            <span>components</span>
          </span>
          <span class="diff-a-pill">
            <span class="diff-a-dot"></span>
            <b>{{ warningCount }}</b>
            <span>warn</span>
          </span>
          <span v-if="visionModel" class="diff-a-pill">
            <span class="diff-a-dot"></span>
            <b>{{ visionModel }}</b>
            <span>model</span>
          </span>
        </div>
        <div class="diff-a-actions">
          <RouterLink
            v-if="resultId"
            class="diff-a-chip diff-a-chip--primary"
            :to="`/results/${resultId}`"
          >
            打开结果
          </RouterLink>
          <button
            class="diff-a-chip"
            type="button"
            :disabled="!resultId"
            @click="activeTab = 'component-identification'"
          >
            回到预览
          </button>
        </div>
      </header>

      <main class="diff-a-board" aria-label="识别工作台">
        <aside class="diff-a-panel">
          <header class="diff-a-panelHeader">
            <div class="diff-a-h">
              <b>输入与任务</b>
              <span>upload · submit · poll</span>
            </div>
            <span class="diff-a-tag">task</span>
          </header>
          <div class="diff-a-panelBody">
            <UploadPanel @submitted="handleSubmitted" />
            <p
              v-if="message"
              class="diff-a-msg"
              :class="message.type"
              role="status"
              aria-live="polite"
            >
              {{ message.text }}
            </p>
            <div class="diff-a-note">
              提交后：中间承接预览与核对，右侧展示运行日志与模型信息。
            </div>
          </div>
        </aside>

        <section class="diff-a-panel">
          <header class="diff-a-panelHeader">
            <div class="diff-a-h">
              <b>预览与核对</b>
              <span>preview · components · rules</span>
            </div>
            <span class="diff-a-tag">preview</span>
          </header>
          <div class="diff-a-panelBody diff-a-panelBody--workbenchPreview">
            <div class="metric-grid metric-grid--workbench">
              <div class="metric compact-metric"><span>总页数</span><b>{{ previewPages.length || '--' }}</b></div>
              <div class="metric compact-metric"><span>检测元件</span><b>{{ components.length }}</b></div>
              <div class="metric compact-metric"><span>规则命中</span><b>{{ combinations.length }}</b></div>
              <div class="metric compact-metric"><span>异常告警</span><b class="warn">{{ warningCount }}</b></div>
            </div>

            <WorkbenchPreviewTabs
              v-if="resultId && (loading || result)"
              class="workbench-primary-preview"
              :components="components"
              :combinations="combinations"
              :previewPages="previewPages"
              :componentTable="componentTable"
              :controlSignalConfiguration="controlSignalConfiguration"
              :titleBlock="titleBlock"
              :activeTab="activeTab"
              :loading="recognitionLoading"
              @update:activeTab="activeTab = $event"
            />

            <div v-else class="diff-a-empty">
              <div>
                <h3>等待识别结果</h3>
                <p>上传图纸并提交后，这里承接预览、标注框与元件标识核对。</p>
              </div>
            </div>
          </div>
        </section>

        <aside class="diff-a-panel">
          <header class="diff-a-panelHeader">
            <div class="diff-a-h">
              <b>运行日志</b>
              <span>model · runtime · steps</span>
            </div>
            <span class="diff-a-tag">log</span>
          </header>
          <div class="diff-a-panelBody">
            <RecognitionLogPanel
              v-if="resultId"
              :entries="logEntries"
              :running="running"
              :model="visionModel || undefined"
            />
            <div v-else class="diff-a-empty diff-a-empty--small">
              <div>
                <h3>暂无日志</h3>
                <p>提交识别任务后，日志会在这里滚动展示。</p>
              </div>
            </div>
          </div>
        </aside>
      </main>
    </section>
  </div>
</template>
