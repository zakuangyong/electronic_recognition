<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import type { ComponentData, PreviewAnnotation, PreviewPage } from '../../types/results'
import { buildLegend, colorForKey, componentColorKey } from '../../app/componentColors'

const props = defineProps<{
  pages: PreviewPage[]
  components: ComponentData[]
  annotations?: PreviewAnnotation[]
}>()

const currentIndex = ref(0)
const zoom = ref(1)
const stageRef = ref<HTMLElement | null>(null)

const MIN_ZOOM = 0.25
const MAX_ZOOM = 4
const ZOOM_STEP = 0.25

// Keep the active page in range when the page set changes.
watch(
  () => props.pages.length,
  (length) => {
    if (currentIndex.value > length - 1) currentIndex.value = Math.max(0, length - 1)
  },
)

const currentPage = computed(() => props.pages[currentIndex.value] ?? null)
const pageSize = computed(() => ({
  width: Math.max(1, Number(currentPage.value?.width) || 1000),
  height: Math.max(1, Number(currentPage.value?.height) || 1000),
}))

const hasCustomAnnotations = computed(() => Array.isArray(props.annotations) && props.annotations.length > 0)

const legend = computed(() => (hasCustomAnnotations.value ? [] : buildLegend(props.components)))

interface OverlayBox {
  left: number
  top: number
  width: number
  height: number
  color: string
  title: string
}

const NON_PREVIEW_REGION_TYPES = new Set([
  'component_table',
  'terminal_table',
  'title_block',
  'table',
  'parts_table',
  'bom_table',
])

function normalizedText(value: unknown): string {
  return typeof value === 'string' ? value.trim().toLowerCase() : ''
}

function isTableRegion(component: ComponentData): boolean {
  const candidates = [
    component.region_type,
    component.region_id,
    component.source,
    component.origin,
    component.route,
    component.kind,
    component.chunk_type,
  ]

  const metadata = component.metadata
  if (metadata && typeof metadata === 'object' && !Array.isArray(metadata)) {
    const record = metadata as Record<string, unknown>
    candidates.push(record.region_type, record.source, record.origin, record.kind)
  }

  return candidates.some((candidate) => {
    const value = normalizedText(candidate)
    return NON_PREVIEW_REGION_TYPES.has(value) || value.includes('table')
  })
}

// Component regions use a 0..1000 normalized coordinate space, so they map
// directly onto percentage offsets regardless of the rendered image size.
const boxes = computed<OverlayBox[]>(() => {
  const page = currentPage.value
  if (!page) return []
  const result: OverlayBox[] = []
  if (hasCustomAnnotations.value) {
    for (const annotation of props.annotations || []) {
      if (annotation.page !== page.page) continue
      const title = annotation.title.trim()
      for (const region of annotation.regions) {
        if (!Array.isArray(region) || region.length !== 4) continue
        const [x0, y0, x1, y1] = region
        const left = (x0 / 1000) * 100
        const top = (y0 / 1000) * 100
        const width = ((x1 - x0) / 1000) * 100
        const height = ((y1 - y0) / 1000) * 100
        if (width <= 0 || height <= 0) continue
        result.push({ left, top, width, height, color: annotation.color, title })
      }
    }
    return result
  }
  for (const component of props.components) {
    if (component.page !== page.page) continue
    if (isTableRegion(component)) continue
    const regions = Array.isArray(component.regions) ? component.regions : []
    const color = colorForKey(componentColorKey(component))
    const title = (component.code || component.label || component.reference_id || '').trim()
    for (const region of regions) {
      if (!Array.isArray(region) || region.length !== 4) continue
      const [x0, y0, x1, y1] = region
      const left = (x0 / 1000) * 100
      const top = (y0 / 1000) * 100
      const width = ((x1 - x0) / 1000) * 100
      const height = ((y1 - y0) / 1000) * 100
      if (width <= 0 || height <= 0) continue
      result.push({ left, top, width, height, color, title })
    }
  }
  return result
})

function prevPage() {
  if (currentIndex.value > 0) currentIndex.value -= 1
}

function nextPage() {
  if (currentIndex.value < props.pages.length - 1) currentIndex.value += 1
}

function zoomIn() {
  zoom.value = Math.min(MAX_ZOOM, Math.round((zoom.value + ZOOM_STEP) * 100) / 100)
}

function zoomOut() {
  zoom.value = Math.max(MIN_ZOOM, Math.round((zoom.value - ZOOM_STEP) * 100) / 100)
}

function computeFitZoom() {
  const stage = stageRef.value
  if (!stage) return 1
  const availableWidth = stage.clientWidth
  const availableHeight = stage.clientHeight
  if (!availableWidth || !availableHeight) return 1
  const fit = Math.min(availableWidth / pageSize.value.width, availableHeight / pageSize.value.height)
  return Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, Math.round(Math.min(fit, 1) * 100) / 100))
}

function resetZoom() {
  zoom.value = computeFitZoom()
}

const canvasStyle = computed(() => ({
  width: `${Math.round(pageSize.value.width * zoom.value)}px`,
}))

watch(
  () => currentPage.value?.page,
  async () => {
    await nextTick()
    resetZoom()
  },
  { immediate: true },
)

onMounted(async () => {
  await nextTick()
  resetZoom()
})
</script>

<template>
  <div class="drawing-preview">
    <div v-if="!pages.length" class="empty-editor">
      <h3>无预览页</h3>
      <p>识别过程中未生成预览页。</p>
    </div>

    <template v-else>
      <div class="drawing-preview-toolbar">
        <div class="drawing-preview-pager">
          <button type="button" class="mini-button" :disabled="currentIndex === 0" @click="prevPage">‹</button>
          <span class="drawing-preview-page-label">第 {{ currentPage?.page }} 页 · {{ currentIndex + 1 }}/{{ pages.length }}</span>
          <button
            type="button"
            class="mini-button"
            :disabled="currentIndex >= pages.length - 1"
            @click="nextPage"
          >›</button>
        </div>
        <div class="drawing-preview-zoom">
          <button type="button" class="mini-button" :disabled="zoom <= MIN_ZOOM" @click="zoomOut">−</button>
          <span class="drawing-preview-zoom-label">{{ Math.round(zoom * 100) }}%</span>
          <button type="button" class="mini-button" :disabled="zoom >= MAX_ZOOM" @click="zoomIn">+</button>
          <button type="button" class="mini-button" @click="resetZoom">适应</button>
        </div>
      </div>

      <ul v-if="legend.length" class="drawing-legend" aria-label="元件类别图例">
        <li v-for="entry in legend" :key="entry.key" class="drawing-legend-item">
          <span class="drawing-legend-swatch" :style="{ background: entry.color }"></span>
          <span class="drawing-legend-text">{{ entry.key }} ({{ entry.count }})</span>
        </li>
      </ul>

      <div ref="stageRef" class="drawing-preview-stage">
        <div class="drawing-preview-canvas" :style="canvasStyle">
          <img v-if="currentPage?.data_url" :src="currentPage.data_url" :alt="`第 ${currentPage.page} 页`" />
          <div
            v-for="(box, index) in boxes"
            :key="index"
            class="drawing-box"
            :style="{
              left: `${box.left}%`,
              top: `${box.top}%`,
              width: `${box.width}%`,
              height: `${box.height}%`,
              borderColor: box.color,
              color: box.color,
            }"
            :title="box.title"
            aria-hidden="true"
          ></div>
        </div>
      </div>
    </template>
  </div>
</template>
