<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { compareDrawings } from '../api/diff'
import type {
  DiffCompareResponse,
  DrawingDiffFileType,
  DiffAllRegionsPage,
} from '../types/diff'

import DiffItemsPanel from '../components/diff/DiffItemsPanel.vue'
import DiffSideBySideViewer from '../components/diff/DiffSideBySideViewer.vue'

import '../app/styles/diff.css'

type Message = { type: 'info' | 'success' | 'error'; text: string }

const oldFile = ref<File | null>(null)
const newFile = ref<File | null>(null)
const fileType = ref<DrawingDiffFileType>('catdrawing')
const dpi = ref(200)
const threshold = ref(30)
const loading = ref(false)
const message = ref<Message | null>(null)
const result = ref<DiffCompareResponse | null>(null)
const supportedTypeHint = '支持 .CATDrawing、.dwg、.pdf'
const activeDiffId = ref<string | null>(null)
const currentPage = ref(1)
const allRegionsPages = ref<DiffAllRegionsPage[]>([])
const navigableIds = ref<string[]>([])

const inferredFileType = computed(() =>
  inferCompatibleFileType(oldFile.value, newFile.value),
)
const fileTypeLabel = computed(() =>
  inferredFileType.value ? formatDrawingFileType(inferredFileType.value) : '--',
)
const fileTypeError = computed(() =>
  getFileTypeError(oldFile.value, newFile.value),
)
const canSubmit = computed(
  () =>
    Boolean(oldFile.value && newFile.value) &&
    !loading.value &&
    !fileTypeError.value,
)
const summary = computed(() => result.value?.data?.summary ?? null)
const diffItems = computed(() => result.value?.data?.diff_items ?? [])
const downloads = computed(() => result.value?.data?.downloads ?? null)
const jobId = computed(() => result.value?.job_id ?? null)
const pageCount = computed(() => summary.value?.page_count ?? 0)
const statusLabel = computed(() => {
  if (loading.value) return '处理中'
  if (summary.value) return '已完成'
  return '未开始'
})
const activeIndex = computed(() => {
  const ids = navigableIds.value.length ? navigableIds.value : diffItems.value.map((i) => i.id)
  return activeDiffId.value ? ids.indexOf(activeDiffId.value) : -1
})

watch([oldFile, newFile], () => {
  const nextType = inferredFileType.value
  if (nextType) fileType.value = nextType
  if (!fileTypeError.value && message.value?.type === 'error') {
    message.value = null
  }
})

watch(
  () => result.value?.job_id,
  async () => {
    allRegionsPages.value = []
    activeDiffId.value = null
    currentPage.value = 1
    const url = result.value?.data?.artifacts?.all_regions_url ?? ''
    if (!url) return
    try {
      const resp = await fetch(url)
      if (!resp.ok) return
      const data = (await resp.json()) as DiffAllRegionsPage[]
      allRegionsPages.value = Array.isArray(data) ? data : []
    } catch {
      allRegionsPages.value = []
    }
    const first = diffItems.value.find((i) => i.page === 1) ?? diffItems.value[0] ?? null
    if (first) activeDiffId.value = first.id
  },
)

async function handleSubmit() {
  if (!oldFile.value || !newFile.value || !canSubmit.value) {
    if (fileTypeError.value) {
      setMessage('error', fileTypeError.value)
    }
    return
  }
  loading.value = true
  result.value = null
  setMessage('info', '正在比对')
  try {
    result.value = await compareDrawings({
      oldFile: oldFile.value,
      newFile: newFile.value,
      fileType: inferredFileType.value ?? fileType.value,
      dpi: dpi.value,
      threshold: threshold.value,
    })
    setMessage('success', `比对完成：${result.value.job_id}`)
  } catch (err) {
    setMessage('error', err instanceof Error ? err.message : '图纸比对失败')
  } finally {
    loading.value = false
  }
}

function handleSelectDiff(id: string) {
  activeDiffId.value = id
  const item = diffItems.value.find((i) => i.id === id)
  if (item) currentPage.value = item.page
}

function handlePrev() {
  const ids = navigableIds.value.length ? navigableIds.value : diffItems.value.map((i) => i.id)
  if (!ids.length) return
  const idx = activeIndex.value
  const next = idx > 0 ? idx - 1 : 0
  handleSelectDiff(ids[next])
}

function handleNext() {
  const ids = navigableIds.value.length ? navigableIds.value : diffItems.value.map((i) => i.id)
  if (!ids.length) return
  const idx = activeIndex.value
  const next = idx >= 0 && idx < ids.length - 1 ? idx + 1 : ids.length - 1
  handleSelectDiff(ids[next])
}

function handleFileChange(kind: 'old' | 'new', event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  if (kind === 'old') oldFile.value = file
  else newFile.value = file
  input.value = ''
}

function clearFile(kind: 'old' | 'new') {
  if (kind === 'old') oldFile.value = null
  else newFile.value = null
}

function setMessage(type: Message['type'], text: string) {
  message.value = { type, text }
}

function formatDrawingFileType(value: DrawingDiffFileType): string {
  const map: Record<DrawingDiffFileType, string> = {
    catdrawing: 'CATDrawing',
    dwg: 'DWG',
    pdf: 'PDF',
  }
  return map[value]
}

function detectDrawingFileType(file: File | null): DrawingDiffFileType | null {
  const filename = file?.name.toLowerCase() ?? ''
  if (filename.endsWith('.catdrawing')) return 'catdrawing'
  if (filename.endsWith('.dwg')) return 'dwg'
  if (filename.endsWith('.pdf')) return 'pdf'
  return null
}

function inferCompatibleFileType(
  oldValue: File | null,
  newValue: File | null,
): DrawingDiffFileType | null {
  const oldType = detectDrawingFileType(oldValue)
  const newType = detectDrawingFileType(newValue)
  if (oldType && newType && oldType === newType) return oldType
  return oldType ?? newType
}

function getFileTypeError(oldValue: File | null, newValue: File | null): string {
  const oldType = detectDrawingFileType(oldValue)
  const newType = detectDrawingFileType(newValue)
  if (oldValue && !oldType) return '旧版文件格式不支持'
  if (newValue && !newType) return '新版文件格式不支持'
  if (oldType && newType && oldType !== newType) return '新旧文件类型不一致'
  return ''
}

function fileLabel(file: File | null) {
  return file?.name || '未选择'
}

function formatSize(file: File | null) {
  if (!file) return '--'
  if (file.size < 1024 * 1024) return `${Math.max(1, Math.round(file.size / 1024))} KB`
  return `${(file.size / 1024 / 1024).toFixed(1)} MB`
}

function formatChangeType(value: string) {
  const map: Record<string, string> = {
    text_changed: '文本变化',
    visual_change: '图形变化',
    graphic_or_text: '图文变化',
  }
  return map[value] || value || '--'
}

function onVisibleIds(ids: string[]) {
  if (
    ids.length === navigableIds.value.length &&
    ids.every((value, index) => value === navigableIds.value[index])
  ) {
    return
  }
  navigableIds.value = [...ids]
}
</script>

<template>
  <div class="diff-a-root">
    <div class="topbar topbar--dark">
      <div>
        <h1>图纸比对</h1>
        <p>SCHEME-A · SIDE-BY-SIDE SYNC</p>
      </div>
      <div class="chips">
        <RouterLink class="chip" to="/workbench">识别工作台</RouterLink>
        <RouterLink class="chip" to="/search">图纸检索</RouterLink>
        <RouterLink class="chip active" to="/drawing-diff">图纸比对</RouterLink>
        <RouterLink class="chip" to="/drawing-correction">图纸纠错</RouterLink>
        <RouterLink class="chip" to="/knowledge">知识库管理</RouterLink>
      </div>
    </div>

    <section class="diff-a-shell" data-testid="diff-shell">
      <header class="diff-a-topbar">
        <div class="diff-a-meta">
          <span class="diff-a-pill">
            <span class="diff-a-dot"></span>
            <b>{{ statusLabel }}</b>
            <span>{{ jobId ? `job ${jobId}` : 'waiting' }}</span>
          </span>
          <span class="diff-a-pill">
            <span class="diff-a-dot"></span>
            <b>{{ fileTypeLabel }}</b>
            <span>type</span>
          </span>
          <span class="diff-a-pill">
            <span class="diff-a-dot"></span>
            <b>{{ summary?.total_diff_count ?? 0 }}</b>
            <span>diff</span>
          </span>
        </div>
        <div class="diff-a-actions">
          <button class="diff-a-chip diff-a-chip--primary" type="button" :disabled="!navigableIds.length" @click="handlePrev">
            上一处
          </button>
          <button class="diff-a-chip diff-a-chip--primary" type="button" :disabled="!navigableIds.length" @click="handleNext">
            下一处
          </button>
          <a v-if="downloads?.summary_json_url" class="diff-a-chip" :href="downloads.summary_json_url" download>JSON</a>
          <a v-if="downloads?.excel_report_url" class="diff-a-chip" :href="downloads.excel_report_url" download>Excel</a>
        </div>
      </header>

      <main class="diff-a-board">
        <aside class="diff-a-panel diff-a-panel--input" data-testid="diff-input-panel">
          <header class="diff-a-panelHeader">
            <div class="diff-a-h">
              <b>比对输入</b>
              <span>old · new · params</span>
            </div>
            <span class="diff-a-tag">compare</span>
          </header>

          <div class="diff-a-panelBody">
            <div class="diff-a-uploadGrid">
              <div class="diff-a-uploadSlot">
                <label class="diff-a-fileBox" :class="{ 'has-file': oldFile }">
                  <span>旧版图纸</span>
                  <strong>{{ fileLabel(oldFile) }}</strong>
                  <small>{{ formatSize(oldFile) }}</small>
                  <input
                    data-testid="diff-old-file"
                    type="file"
                    accept=".CATDrawing,.dwg,.pdf,application/pdf"
                    @change="handleFileChange('old', $event)"
                  />
                </label>
                <button v-if="oldFile" class="diff-a-clear" type="button" aria-label="清除旧版图纸" @click="clearFile('old')">
                  ×
                </button>
              </div>

              <div class="diff-a-uploadSlot">
                <label class="diff-a-fileBox" :class="{ 'has-file': newFile }">
                  <span>新版图纸</span>
                  <strong>{{ fileLabel(newFile) }}</strong>
                  <small>{{ formatSize(newFile) }}</small>
                  <input
                    data-testid="diff-new-file"
                    type="file"
                    accept=".CATDrawing,.dwg,.pdf,application/pdf"
                    @change="handleFileChange('new', $event)"
                  />
                </label>
                <button v-if="newFile" class="diff-a-clear" type="button" aria-label="清除新版图纸" @click="clearFile('new')">
                  ×
                </button>
              </div>
            </div>

            <div class="diff-a-formGrid">
              <label class="diff-a-field diff-a-field--hint">
                <span>文件类型</span>
                <small>{{ supportedTypeHint }}</small>
              </label>
              <label class="diff-a-field">
                <span>DPI</span>
                <input v-model.number="dpi" type="number" min="72" max="1200" />
              </label>
              <label class="diff-a-field">
                <span>阈值</span>
                <input v-model.number="threshold" type="number" min="0" max="255" />
              </label>
            </div>

            <button class="diff-a-start" type="button" :disabled="!canSubmit" @click="handleSubmit">
              {{ loading ? '处理中' : '开始比对' }}
            </button>

            <p
              v-if="message || fileTypeError"
              class="diff-a-msg"
              :class="message?.type || 'error'"
              role="status"
              aria-live="polite"
            >
              {{ fileTypeError || message?.text }}
            </p>
          </div>
        </aside>

        <DiffSideBySideViewer
          :job-id="jobId"
          :page="currentPage"
          :page-count="pageCount"
          :diff-items="diffItems"
          :all-regions-pages="allRegionsPages"
          :active-id="activeDiffId"
          @update:page="currentPage = $event"
        />

        <DiffItemsPanel
          :items="diffItems.filter((i) => i.page === currentPage)"
          :active-id="activeDiffId"
          :page="currentPage"
          @select="handleSelectDiff"
          @visible-ids="onVisibleIds"
        />
      </main>
    </section>
  </div>
</template>
