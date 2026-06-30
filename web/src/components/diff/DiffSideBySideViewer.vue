<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import type { DiffAllRegionsPage, DiffItem } from '../../types/diff'

const props = defineProps<{
  jobId: string | null
  page: number
  pageCount: number
  diffItems: DiffItem[]
  allRegionsPages: DiffAllRegionsPage[]
  activeId: string | null
}>()

const emit = defineEmits<{
  (e: 'update:page', value: number): void
  (e: 'reset'): void
  (e: 'focus'): void
}>()

type World = { x: number; y: number; scale: number }

const viewportOld = ref<HTMLElement | null>(null)
const viewportNew = ref<HTMLElement | null>(null)
const worldOld = ref<HTMLElement | null>(null)
const worldNew = ref<HTMLElement | null>(null)
const stageOld = ref<HTMLElement | null>(null)
const stageNew = ref<HTMLElement | null>(null)
const imgOld = ref<HTMLImageElement | null>(null)
const imgNew = ref<HTMLImageElement | null>(null)
const overlayOld = ref<HTMLElement | null>(null)
const overlayNew = ref<HTMLElement | null>(null)

const world = ref<World>({ x: 0, y: 0, scale: 0.5 })
const dragging = ref<
  | {
      startX: number
      startY: number
      worldX: number
      worldY: number
    }
  | null
>(null)

const imgSize = ref({ w: 1, h: 1 })

const isOverview = computed(() => world.value.scale <= 0.09)
const activeItem = computed(() => {
  if (!props.activeId) return null
  return props.diffItems.find((i) => i.id === props.activeId) ?? null
})
const worldData = computed(() => {
  return `${Math.round(world.value.x)},${Math.round(world.value.y)},${world.value.scale.toFixed(3)}`
})

const pendingFocusId = ref<string | null>(null)

const pageOldUrl = computed(() => {
  if (!props.jobId) return ''
  return `/api/diff/files/${props.jobId}/work/rendered/old_page_${String(props.page).padStart(3, '0')}.png`
})

const pageNewUrl = computed(() => {
  if (!props.jobId) return ''
  return `/api/diff/files/${props.jobId}/work/rendered/new_page_${String(props.page).padStart(3, '0')}.png`
})

const zoomLabel = computed(() => `${Math.round(world.value.scale * 100)}%`)

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value))
}

function setWorld(next: Partial<World>) {
  world.value = { ...world.value, ...next }
  const t = `translate(${world.value.x}px, ${world.value.y}px) scale(${world.value.scale})`
  if (worldOld.value) worldOld.value.style.transform = t
  if (worldNew.value) worldNew.value.style.transform = t
  updateOverlayScaleHints()
}

function updateOverlayScaleHints() {
  const inv = 1 / Math.max(0.01, world.value.scale)
  const invOverview = isOverview.value ? inv * 0.62 : inv
  const apply = (el: HTMLElement | null) => {
    if (!el) return
    el.style.setProperty('--inv', String(inv))
    el.style.setProperty('--invOverview', String(invOverview))
  }
  apply(overlayOld.value)
  apply(overlayNew.value)
}

function computeFitWorld(): World {
  const view = viewportNew.value?.getBoundingClientRect()
  if (!view) return { x: 0, y: 0, scale: 0.5 }
  const pad = 22
  const vw = Math.max(240, view.width - pad * 2)
  const vh = Math.max(180, view.height - pad * 2)
  const s = clamp(Math.min(vw / imgSize.value.w, vh / imgSize.value.h) * 0.985, 0.06, 1.2)
  const x = Math.round((view.width - imgSize.value.w * s) / 2)
  const y = Math.round((view.height - imgSize.value.h * s) / 2)
  return { x, y, scale: s }
}

function computeResetWorld(): World {
  const view = viewportNew.value?.getBoundingClientRect()
  if (!view) return { x: 0, y: 0, scale: 0.06 }
  const s = 0.06
  const x = Math.round((view.width - imgSize.value.w * s) / 2)
  const y = Math.round((view.height - imgSize.value.h * s) / 2)
  return { x, y, scale: s }
}

function focusToItem(item: DiffItem) {
  const view = viewportNew.value?.getBoundingClientRect()
  if (!view) return
  const [x1, y1, x2, y2] = item.bbox
  const cx = (x1 + x2) / 2
  const cy = (y1 + y2) / 2
  const sTarget = isOverview.value ? 0.6 : world.value.scale
  const x = view.width / 2 - cx * sTarget
  const y = view.height / 2 - cy * sTarget
  setWorld({ x, y, scale: sTarget })
}

function onWheel(e: WheelEvent) {
  e.preventDefault()
  const view = (e.currentTarget as HTMLElement).getBoundingClientRect()
  const mx = e.clientX - view.left
  const my = e.clientY - view.top
  const delta = e.deltaY < 0 ? 1.08 : 1 / 1.08
  const nextScale = clamp(world.value.scale * delta, 0.18, 3.0)
  const scaleRatio = nextScale / world.value.scale
  const nextX = mx - (mx - world.value.x) * scaleRatio
  const nextY = my - (my - world.value.y) * scaleRatio
  setWorld({ x: nextX, y: nextY, scale: nextScale })
}

function onDown(e: PointerEvent) {
  e.preventDefault()
  dragging.value = {
    startX: e.clientX,
    startY: e.clientY,
    worldX: world.value.x,
    worldY: world.value.y,
  }
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
}

function onMove(e: PointerEvent) {
  if (!dragging.value) return
  const dx = e.clientX - dragging.value.startX
  const dy = e.clientY - dragging.value.startY
  setWorld({ x: dragging.value.worldX + dx, y: dragging.value.worldY + dy })
}

function onUp() {
  dragging.value = null
}

function ensureStageSize() {
  const w = imgSize.value.w
  const h = imgSize.value.h
  if (stageOld.value) {
    stageOld.value.style.width = `${w}px`
    stageOld.value.style.height = `${h}px`
  }
  if (stageNew.value) {
    stageNew.value.style.width = `${w}px`
    stageNew.value.style.height = `${h}px`
  }
}

function updateFromImage() {
  const w = imgNew.value?.naturalWidth || imgOld.value?.naturalWidth || 0
  const h = imgNew.value?.naturalHeight || imgOld.value?.naturalHeight || 0
  if (w > 0 && h > 0) {
    imgSize.value = { w, h }
    ensureStageSize()
    setWorld(computeFitWorld())
    if (pendingFocusId.value && activeItem.value && activeItem.value.page === props.page) {
      focusToItem(activeItem.value)
      pendingFocusId.value = null
    }
  }
}

function overviewClass(item: DiffItem) {
  return isOverview.value ? 'overview' : ''
}

function regionStyle(item: DiffItem) {
  const [x1, y1, x2, y2] = item.bbox
  const w = imgSize.value.w
  const h = imgSize.value.h
  const left = (x1 / w) * 100
  const top = (y1 / h) * 100
  const width = ((x2 - x1) / w) * 100
  const height = ((y2 - y1) / h) * 100
  return {
    left: `${left}%`,
    top: `${top}%`,
    width: `${width}%`,
    height: `${height}%`,
  }
}

function handleReset() {
  setWorld(computeResetWorld())
  emit('reset')
}

function handleFocus() {
  if (activeItem.value) focusToItem(activeItem.value)
  emit('focus')
}

watch(
  () => props.page,
  async () => {
    await nextTick()
    updateFromImage()
  },
)

watch(
  () => props.activeId,
  async (next, prev) => {
    if (!next || next === prev) return
    if (!activeItem.value) return
    pendingFocusId.value = next
    await nextTick()
    if (activeItem.value.page !== props.page) return
    focusToItem(activeItem.value)
    pendingFocusId.value = null
  },
)

onMounted(async () => {
  await nextTick()
  updateFromImage()
})
</script>

<template>
  <section class="diff-a-panel diff-a-panel--viewer" data-testid="diff-viewer" :data-world="worldData">
    <header class="diff-a-viewerTop">
      <div class="diff-a-viewerRow">
        <div class="diff-a-pills">
          <span class="diff-a-pill">
            <span class="diff-a-dot"></span>
            <b>联动</b>
            <span>平移/缩放/页码</span>
          </span>
          <span class="diff-a-pill">
            <span class="diff-a-dot"></span>
            <b data-testid="diff-zoom">{{ zoomLabel }}</b>
            <span>缩放</span>
          </span>
          <span class="diff-a-pill">
            <span class="diff-a-dot"></span>
            <b>{{ page }}</b>
            <span>/ {{ pageCount || '--' }}</span>
          </span>
        </div>

        <div class="diff-a-controls">
          <button class="diff-a-chip" type="button" @click="handleReset">复位视图</button>
          <button class="diff-a-chip diff-a-chip--primary" type="button" :disabled="!activeId" @click="handleFocus">
            定位差异
          </button>
        </div>
      </div>

      <div class="diff-a-viewerRow diff-a-viewerRow--bottom">
        <label class="diff-a-pageSelect">
          <span>页码</span>
          <select :value="page" @change="emit('update:page', Number(($event.target as HTMLSelectElement).value))">
            <option v-for="n in pageCount" :key="n" :value="n">第 {{ n }} 页</option>
          </select>
        </label>
        <div class="diff-a-active">
          <span>当前差异</span>
          <b data-testid="diff-active-id">{{ activeId || '--' }}</b>
        </div>
      </div>
    </header>

    <div class="diff-a-viewerGrid">
      <div class="diff-a-pane">
        <div class="diff-a-paneHead">
          <div class="diff-a-paneTitle">
            <span class="diff-a-badge diff-a-badge--old">OLD</span>
          </div>
          <span class="diff-a-badge">page {{ page }}</span>
        </div>
        <div
          ref="viewportOld"
          class="diff-a-viewport"
          @wheel="onWheel"
          @pointerdown="onDown"
          @pointermove="onMove"
          @pointerup="onUp"
          @pointercancel="onUp"
          @pointerleave="onUp"
        >
          <div ref="worldOld" class="diff-a-world">
            <div ref="stageOld" class="diff-a-stage">
              <img ref="imgOld" class="diff-a-img" :src="pageOldUrl" alt="旧版图纸" draggable="false" @load="updateFromImage" />
              <div ref="overlayOld" class="diff-a-overlay" :data-overview="isOverview ? '1' : '0'">
                <div
                  v-for="item in diffItems.filter((i) => i.page === page)"
                  :key="`old-${item.id}`"
                  class="diff-a-region"
                  :class="[
                    item.id === activeId ? 'active' : '',
                    !isOverview && activeId && item.id !== activeId ? 'dim' : '',
                    overviewClass(item),
                  ]"
                  :style="regionStyle(item)"
                ></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="diff-a-pane">
        <div class="diff-a-paneHead">
          <div class="diff-a-paneTitle">
            <span class="diff-a-badge diff-a-badge--new">NEW</span>
          </div>
          <span class="diff-a-badge">page {{ page }}</span>
        </div>
        <div
          ref="viewportNew"
          class="diff-a-viewport"
          @wheel="onWheel"
          @pointerdown="onDown"
          @pointermove="onMove"
          @pointerup="onUp"
          @pointercancel="onUp"
          @pointerleave="onUp"
        >
          <div ref="worldNew" class="diff-a-world">
            <div ref="stageNew" class="diff-a-stage">
              <img ref="imgNew" class="diff-a-img" :src="pageNewUrl" alt="新版图纸" draggable="false" @load="updateFromImage" />
              <div ref="overlayNew" class="diff-a-overlay" :data-overview="isOverview ? '1' : '0'">
                <div
                  v-for="item in diffItems.filter((i) => i.page === page)"
                  :key="`new-${item.id}`"
                  class="diff-a-region"
                  :class="[
                    item.id === activeId ? 'active' : '',
                    !isOverview && activeId && item.id !== activeId ? 'dim' : '',
                    overviewClass(item),
                  ]"
                  :style="regionStyle(item)"
                ></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
