<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import UploadPanel from '../components/workbench/UploadPanel.vue'
import DrawingPreview from '../components/workbench/DrawingPreview.vue'
import RecognitionLogPanel from '../components/workbench/RecognitionLogPanel.vue'
import { useResultPolling } from '../composables/useResultPolling'
import type {
  AnalyzeResponse,
  ComponentData,
  LogEntry,
  PreviewPage,
} from '../types/results'
import { fetchConfig } from '../api/config'

import '../app/styles/diff.css'

type Message = { type: 'info' | 'success' | 'error'; text: string }

type BomEntry = {
  code: string
  label: string
  quantity: number | null
}

type RecognizedEntry = {
  code: string
  label: string
  quantity: number
}

const task = ref<AnalyzeResponse | null>(null)
const message = ref<Message | null>(null)
const visionModel = ref<string | null>(null)
const rawExpanded = ref(false)

const { result, steps, loading, startPolling } = useResultPolling()

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
const previewPages = computed<PreviewPage[]>(() => arrayPayload<PreviewPage>('preview_pages', result.value?.preview_pages))
const componentTable = computed(() => objectPayload('component_table', result.value?.component_table))

const logEntries = computed<LogEntry[]>(() => {
  const raw = (steps.value?.steps as Record<string, unknown> | undefined)?.recognition_log
  return Array.isArray(raw) ? (raw as LogEntry[]) : []
})

function setMessage(type: Message['type'], text: string) {
  message.value = { type, text }
}

function handleSubmitted(payload: AnalyzeResponse) {
  task.value = payload
  message.value = null
  rawExpanded.value = false
  if (payload.result_id) {
    startPolling(payload.result_id)
    setMessage('success', `任务已提交：${payload.result_id}`)
  } else {
    setMessage('error', '提交成功但未返回结果 ID')
  }
}

function normalizedText(value: unknown): string {
  return typeof value === 'string' ? value.trim().toLowerCase() : ''
}

function codeTokens(value: unknown): string[] {
  if (typeof value !== 'string') return []
  return value
    .split(/[\s,，/|+]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function asString(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number') return String(value)
  return ''
}

function pickString(row: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = row[key]
    const text = asString(value)
    if (text) return text
  }
  return ''
}

function pickNumber(row: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    const value = row[key]
    if (typeof value === 'number' && Number.isFinite(value)) return value
    if (typeof value === 'string') {
      const trimmed = value.trim()
      if (!trimmed) continue
      const parsed = Number(trimmed)
      if (Number.isFinite(parsed)) return parsed
    }
  }
  return null
}

function normalizeRows(payload: unknown): Array<Record<string, unknown>> {
  if (Array.isArray(payload)) {
    return payload.filter((row) => typeof row === 'object' && row !== null) as Array<Record<string, unknown>>
  }
  if (payload && typeof payload === 'object') {
    const asAny = payload as Record<string, unknown>
    const rows = asAny.rows
    if (Array.isArray(rows)) {
      return rows.filter((row) => typeof row === 'object' && row !== null) as Array<Record<string, unknown>>
    }
  }
  return []
}

const bomEntries = computed<BomEntry[]>(() => {
  const rows = normalizeRows(componentTable.value)
  return rows
    .map((row) => {
      const code = pickString(row, [
        '元件代号',
        '代号',
        '位号',
        '标号',
        'code',
        'designation',
        'tag',
        'TAG',
      ])
      const label = pickString(row, [
        '元件名称',
        '名称',
        'label',
        'name',
        'device',
        'desc',
        'description',
      ])
      const quantity = pickNumber(row, ['数量', 'qty', 'quantity', 'count', 'num'])
      return { code: code.trim(), label: label.trim(), quantity }
    })
    .filter((entry) => entry.code.length > 0)
})

function componentQuantity(comp: ComponentData): number {
  if (typeof comp.occurrence_count === 'number' && Number.isFinite(comp.occurrence_count)) {
    return Math.max(1, Math.round(comp.occurrence_count))
  }
  if (Array.isArray(comp.regions) && comp.regions.length > 0) return comp.regions.length
  return 1
}

const recognizedEntries = computed<RecognizedEntry[]>(() => {
  const map = new Map<string, RecognizedEntry>()
  for (const component of components.value) {
    const label = (component.label || '').trim()
    const quantity = componentQuantity(component)
    const tokens = codeTokens(component.code)
    const codes = tokens.length ? tokens : []
    for (const code of codes) {
      const key = normalizedText(code)
      if (!key) continue
      const existing = map.get(key)
      if (existing) {
        existing.quantity += quantity
        if (!existing.label && label) existing.label = label
        continue
      }
      map.set(key, { code: code.trim(), label, quantity })
    }
  }
  return Array.from(map.values()).sort((a, b) => a.code.localeCompare(b.code, 'zh-Hans-CN'))
})

const bomMap = computed(() => {
  const map = new Map<string, BomEntry>()
  for (const entry of bomEntries.value) {
    const key = normalizedText(entry.code)
    if (!key) continue
    if (!map.has(key)) map.set(key, entry)
  }
  return map
})

const recognizedMap = computed(() => {
  const map = new Map<string, RecognizedEntry>()
  for (const entry of recognizedEntries.value) {
    const key = normalizedText(entry.code)
    if (!key) continue
    if (!map.has(key)) map.set(key, entry)
  }
  return map
})

const missingInBom = computed(() => {
  const missing: RecognizedEntry[] = []
  for (const entry of recognizedEntries.value) {
    if (!bomMap.value.has(normalizedText(entry.code))) missing.push(entry)
  }
  return missing
})

const missingInRecognition = computed(() => {
  const missing: BomEntry[] = []
  for (const entry of bomEntries.value) {
    if (!recognizedMap.value.has(normalizedText(entry.code))) missing.push(entry)
  }
  return missing
})

const nameMismatches = computed(() => {
  const mismatches: Array<{ code: string; bomLabel: string; recognizedLabel: string }> = []
  for (const entry of recognizedEntries.value) {
    const bom = bomMap.value.get(normalizedText(entry.code))
    if (!bom) continue
    const left = normalizedText(bom.label)
    const right = normalizedText(entry.label)
    if (left && right && left !== right) {
      mismatches.push({ code: entry.code, bomLabel: bom.label, recognizedLabel: entry.label })
    }
  }
  return mismatches
})

const quantityMismatches = computed(() => {
  const mismatches: Array<{ code: string; bomQuantity: number; recognizedQuantity: number }> = []
  for (const entry of recognizedEntries.value) {
    const bom = bomMap.value.get(normalizedText(entry.code))
    if (!bom || bom.quantity == null) continue
    if (bom.quantity !== entry.quantity) {
      mismatches.push({ code: entry.code, bomQuantity: bom.quantity, recognizedQuantity: entry.quantity })
    }
  }
  return mismatches
})

const mismatchCount = computed(() => (
  missingInBom.value.length
  + missingInRecognition.value.length
  + nameMismatches.value.length
  + quantityMismatches.value.length
))

const correctionReport = computed(() => {
  if (!resultId.value) return null
  return {
    result_id: resultId.value,
    status: status.value || null,
    generated_at: new Date().toISOString(),
    scope: 'circuit',
    summary: {
      bom_entries: bomEntries.value.length,
      recognized_entries: recognizedEntries.value.length,
      missing_in_bom: missingInBom.value.length,
      missing_in_recognition: missingInRecognition.value.length,
      name_mismatches: nameMismatches.value.length,
      quantity_mismatches: quantityMismatches.value.length,
    },
    missing_in_bom: missingInBom.value,
    missing_in_recognition: missingInRecognition.value,
    name_mismatches: nameMismatches.value,
    quantity_mismatches: quantityMismatches.value,
  }
})

function downloadJson(filename: string, payload: unknown) {
  const text = JSON.stringify(payload ?? {}, null, 2)
  const blob = new Blob([text], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

function exportReport() {
  if (!correctionReport.value) return
  const filename = `drawing-correction-${resultId.value}.json`
  downloadJson(filename, correctionReport.value)
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
        <h1>图纸纠错</h1>
        <p>CORRECTION · RECOGNIZE → COMPARE → FIX</p>
      </div>
      <div class="chips">
        <RouterLink class="chip" to="/workbench">识别工作台</RouterLink>
        <RouterLink class="chip" to="/search">图纸检索</RouterLink>
        <RouterLink class="chip" to="/drawing-diff">图纸比对</RouterLink>
        <RouterLink class="chip active" to="/drawing-correction">图纸纠错</RouterLink>
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
            <b>{{ recognizedEntries.length }}</b>
            <span>recognized</span>
          </span>
          <span class="diff-a-pill">
            <span class="diff-a-dot"></span>
            <b>{{ bomEntries.length }}</b>
            <span>bom</span>
          </span>
          <span class="diff-a-pill">
            <span class="diff-a-dot"></span>
            <b>{{ mismatchCount }}</b>
            <span>mismatch</span>
          </span>
          <span class="diff-a-pill">
            <span class="diff-a-dot"></span>
            <b>电路图</b>
            <span>enabled</span>
          </span>
          <span class="diff-a-pill" style="opacity: 0.7">
            <span class="diff-a-dot"></span>
            <b>工程图</b>
            <span>coming</span>
          </span>
          <span v-if="visionModel" class="diff-a-pill">
            <span class="diff-a-dot"></span>
            <b>{{ visionModel }}</b>
            <span>model</span>
          </span>
        </div>
        <div class="diff-a-actions">
          <button class="diff-a-chip diff-a-chip--primary" type="button" :disabled="!correctionReport" @click="exportReport">
            导出纠错报告
          </button>
          <button class="diff-a-chip" type="button" disabled aria-disabled="true">
            写回 BOM（待接入）
          </button>
        </div>
      </header>

      <main class="diff-a-board" aria-label="图纸纠错">
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
              纠错范围：电路图纸元件识别结果 ↔ 图纸标签表(BOM)字段。工程图纸纠错后续补充。
            </div>
          </div>
        </aside>

        <section class="diff-a-panel">
          <header class="diff-a-panelHeader">
            <div class="diff-a-h">
              <b>预览与纠错</b>
              <span>preview · compare</span>
            </div>
            <span class="diff-a-tag">correction</span>
          </header>
          <div class="diff-a-panelBody diff-a-panelBody--workbenchPreview">
            <div v-if="!resultId" class="empty-editor">
              <h3>未开始纠错</h3>
              <p>上传图纸并开始识别后，这里会展示预览和 BOM 对比结果。</p>
            </div>

            <div v-else class="component-identification-split">
              <div class="preview-box preview-box--hero component-identification-preview">
                <DrawingPreview :pages="previewPages" :components="components" />
              </div>

              <section class="component-identification-side">
                <div class="component-identification-title">
                  <b>纠错对比</b>
                  <span class="label">components ↔ bom</span>
                </div>

                <div class="component-identification-list" aria-label="纠错对比面板">
                  <div class="label-compare-card">
                    <div class="label-compare-summary">
                      <article>
                        <span>BOM 行数</span>
                        <strong>{{ bomEntries.length }}</strong>
                      </article>
                      <article>
                        <span>识别代号</span>
                        <strong>{{ recognizedEntries.length }}</strong>
                      </article>
                      <article>
                        <span>识别缺失</span>
                        <strong>{{ missingInRecognition.length }}</strong>
                      </article>
                      <article>
                        <span>BOM 缺失</span>
                        <strong>{{ missingInBom.length }}</strong>
                      </article>
                    </div>

                    <div class="label-compare-section">
                      <h4>名称不一致</h4>
                      <div v-if="nameMismatches.length" class="component-table-wrap">
                        <table class="component-table label-compare-table">
                          <thead>
                            <tr>
                              <th>代号</th>
                              <th>BOM</th>
                              <th>识别</th>
                            </tr>
                          </thead>
                          <tbody>
                            <tr v-for="item in nameMismatches" :key="item.code">
                              <td class="mono">{{ item.code }}</td>
                              <td class="mono">{{ item.bomLabel || '--' }}</td>
                              <td class="mono">{{ item.recognizedLabel || '--' }}</td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                      <div v-else class="empty-editor">
                        <h3>无名称差异</h3>
                        <p>识别名称与 BOM 名称暂未发现冲突。</p>
                      </div>
                    </div>

                    <div class="label-compare-section">
                      <h4>数量不一致（仅在 BOM 提供数量时对比）</h4>
                      <div v-if="quantityMismatches.length" class="component-table-wrap">
                        <table class="component-table label-compare-table">
                          <thead>
                            <tr>
                              <th>代号</th>
                              <th>BOM 数量</th>
                              <th>识别数量</th>
                            </tr>
                          </thead>
                          <tbody>
                            <tr v-for="item in quantityMismatches" :key="item.code">
                              <td class="mono">{{ item.code }}</td>
                              <td class="mono">{{ item.bomQuantity }}</td>
                              <td class="mono">{{ item.recognizedQuantity }}</td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                      <div v-else class="empty-editor">
                        <h3>无数量差异</h3>
                        <p>暂未发现识别数量与 BOM 数量冲突。</p>
                      </div>
                    </div>

                    <div class="label-compare-section">
                      <h4>识别存在但 BOM 缺失</h4>
                      <div v-if="missingInBom.length" class="component-table-wrap">
                        <table class="component-table label-compare-table">
                          <thead>
                            <tr>
                              <th>代号</th>
                              <th>识别名称</th>
                              <th>识别数量</th>
                            </tr>
                          </thead>
                          <tbody>
                            <tr v-for="item in missingInBom" :key="item.code">
                              <td class="mono">{{ item.code }}</td>
                              <td class="mono">{{ item.label || '--' }}</td>
                              <td class="mono">{{ item.quantity }}</td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                      <div v-else class="empty-editor">
                        <h3>无 BOM 缺失项</h3>
                        <p>识别出的代号均能在 BOM 中找到对应行。</p>
                      </div>
                    </div>

                    <div class="label-compare-section">
                      <h4>BOM 存在但识别缺失</h4>
                      <div v-if="missingInRecognition.length" class="component-table-wrap">
                        <table class="component-table label-compare-table">
                          <thead>
                            <tr>
                              <th>代号</th>
                              <th>BOM 名称</th>
                              <th>BOM 数量</th>
                            </tr>
                          </thead>
                          <tbody>
                            <tr v-for="item in missingInRecognition" :key="item.code">
                              <td class="mono">{{ item.code }}</td>
                              <td class="mono">{{ item.label || '--' }}</td>
                              <td class="mono">{{ item.quantity == null ? '--' : item.quantity }}</td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                      <div v-else class="empty-editor">
                        <h3>无识别缺失项</h3>
                        <p>BOM 中的代号均能在识别结果中找到匹配。</p>
                      </div>
                    </div>
                  </div>

                  <div class="result-card" style="margin-top: 10px">
                    <div class="panel-title panel-title--tight">
                      <b>图纸标签表（原始）</b>
                      <span class="label">component_table</span>
                    </div>
                    <div class="badge-row" style="margin-top: 10px">
                      <button class="button" type="button" @click="rawExpanded = !rawExpanded">
                        {{ rawExpanded ? '收起原始 JSON' : '展开原始 JSON' }}
                      </button>
                      <button class="button" type="button" :disabled="!resultId" @click="downloadJson(`component-table-${resultId}.json`, componentTable)">
                        导出 component_table
                      </button>
                    </div>
                    <pre v-if="rawExpanded" style="margin-top: 10px">{{ JSON.stringify(componentTable ?? {}, null, 2) }}</pre>
                    <div v-else-if="!Object.keys(componentTable).length" class="empty-editor" style="margin-top: 10px">
                      <h3>暂无图纸标签表</h3>
                      <p>后端未返回 component_table 或字段为空。</p>
                    </div>
                  </div>
                </div>
              </section>
            </div>
          </div>
        </section>

        <aside class="diff-a-panel">
          <header class="diff-a-panelHeader">
            <div class="diff-a-h">
              <b>运行日志</b>
              <span>recognition</span>
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
            <div v-else class="empty-editor">
              <h3>无日志</h3>
              <p>开始识别后，这里会展示识别日志与模型信息。</p>
            </div>
            <p class="message info" v-if="recognitionLoading" role="status">识别任务执行中：对比将随着步骤结果实时刷新。</p>
          </div>
        </aside>
      </main>
    </section>
  </div>
</template>

