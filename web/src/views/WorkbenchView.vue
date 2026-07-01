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

defineOptions({ name: 'WorkbenchView' })

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

function payloadCount(payload: unknown): number {
  if (Array.isArray(payload)) return payload.length
  if (payload && typeof payload === 'object') return Object.keys(payload as Record<string, unknown>).length
  return 0
}

function payloadHasValue(payload: unknown): boolean {
  if (payload == null) return false
  if (Array.isArray(payload)) return payload.length > 0
  if (typeof payload === 'object') return Object.keys(payload as Record<string, unknown>).length > 0
  return true
}

function stepLogMessage(name: string, payload: unknown): string | null {
  const count = payloadCount(payload)
  const messages: Record<string, string> = {
    document: '图纸解析完成，开始提取页面与文本。',
    title_block: '图签信息提取完成。',
    control_signal_configuration: '控制与信号配置提取完成。',
    component_table: '图纸标签表提取完成。',
    page_quality: `页面质量分析完成，共 ${count} 页。`,
    layout_regions: `版面区域分析完成，共 ${count} 条记录。`,
    structured_region_extraction: `结构化区域提取完成，共 ${count} 条记录。`,
    open_symbols: `开放识别已发现 ${count} 条元器件记录。`,
    open_recognition_tiles: count
      ? `图纸整页识别切片已处理 ${count} 条记录。`
      : '已准备图纸整页图，准备调用视觉模型。',
    open_categories: `开放识别类别已聚合，共 ${count} 种。`,
    rag_corrections: `知识库名称修正已处理 ${count} 种元器件。`,
    detected_components: `元器件识别完成，共形成 ${count} 条结果。`,
    detected_combinations: `组合规则判断完成，共识别 ${count} 个组合。`,
    preview_pages: `预览页面生成完成，共 ${count} 页。`,
    warnings: `识别过程产生 ${count} 条提示。`,
    meta: '运行元信息已生成。',
  }
  if (messages[name]) return messages[name]
  if (!payloadHasValue(payload)) return null
  return `步骤 ${name} 已完成。`
}

function currentLocalLogTime(): string {
  const date = new Date()
  const pad = (value: number) => String(value).padStart(2, '0')
  const offsetMinutes = -date.getTimezoneOffset()
  const offsetSign = offsetMinutes >= 0 ? '+' : '-'
  const absoluteOffset = Math.abs(offsetMinutes)
  const offsetHours = Math.floor(absoluteOffset / 60)
  const offsetRestMinutes = absoluteOffset % 60
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}${offsetSign}${pad(offsetHours)}:${pad(offsetRestMinutes)}`
}

function fallbackStepLogTime(entries: LogEntry[]): string {
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    const time = entries[index]?.time
    if (typeof time === 'string' && time.trim()) return time
  }
  return currentLocalLogTime()
}

function stepSyntheticLogEntries(time: string): LogEntry[] {
  return Object.entries(stepPayloads.value)
    .filter(([name]) => name !== 'recognition_log')
    .flatMap(([name, payload]) => {
      const message = stepLogMessage(name, payload)
      if (!message) return []
      return [{
        time,
        stage: `step:${name}`,
        level: 'info',
        message,
      }]
    })
}

const logEntries = computed<LogEntry[]>(() => {
  const raw = stepPayloads.value.recognition_log
  const entries = Array.isArray(raw) ? (raw as LogEntry[]) : []
  const seenStages = new Set(entries.map((entry) => entry.stage))
  const synthetic = stepSyntheticLogEntries(fallbackStepLogTime(entries)).filter((entry) => {
    const backendStage = entry.stage.replace(/^step:/, '')
    return !seenStages.has(backendStage) && !seenStages.has(entry.stage)
  })
  return [...entries, ...synthetic]
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
