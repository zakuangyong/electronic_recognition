<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { buildApiUrl } from '../../api/http'
import type { SearchResultItem } from '../../types/search'

const props = defineProps<{
  open: boolean
  item: SearchResultItem | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const currentPage = ref<number | null>(null)

const pages = computed(() => props.item?.matched_pages ?? [])
const isInternalPreview = computed(() => {
  const url = props.item?.preview_url
  return !url || url.startsWith('/results/') || url.startsWith('/api/results/')
})
const previewBaseUrl = computed(() => {
  if (!props.item) return ''
  if (isInternalPreview.value) {
    return buildApiUrl(`/api/results/${props.item.result_id}/preview-file`)
  }
  const previewUrl = props.item.preview_url ?? ''
  return previewUrl.split('#')[0] || previewUrl
})

function previewPageUrl(page: number): string {
  if (!props.item) return ''
  if (isInternalPreview.value) {
    return buildApiUrl(`/api/results/${props.item.result_id}/preview-page/${page}`)
  }
  return `${previewBaseUrl.value}#page-${page}`
}

watch(
  () => [props.open, props.item?.result_id, props.item?.matched_pages?.join(',')],
  () => {
    currentPage.value = pages.value[0] ?? null
  },
  { immediate: true },
)

const frameUrl = computed(() => {
  if (!props.item) return ''
  if (currentPage.value == null) {
    return previewBaseUrl.value
  }
  return previewPageUrl(currentPage.value)
})

const previewTitle = computed(() => props.item?.drawing_title || props.item?.filename || 'drawing preview')
const shouldScalePageImage = computed(() => isInternalPreview.value && currentPage.value != null)
</script>

<template>
  <teleport to="body">
    <div
      v-if="open && item"
      class="search-preview-modal"
      role="dialog"
      aria-modal="true"
      aria-label="打开图纸预览"
    >
      <div class="search-preview-backdrop" @click="emit('close')" />
      <section class="search-preview-panel">
        <header class="search-preview-header">
          <div>
            <strong>打开图纸预览</strong>
            <p>{{ item.drawing_title || item.filename }} · {{ item.drawing_number || '未标注图号' }}</p>
          </div>
          <button type="button" data-action="close-preview" @click="emit('close')">关闭</button>
        </header>

        <div class="search-preview-body">
          <aside class="search-preview-nav">
            <button
              v-for="page in pages"
              :key="page"
              type="button"
              class="search-preview-page"
              :class="{ active: page === currentPage }"
              @click="currentPage = page"
            >
              第 {{ page }} 页
            </button>
            <p v-if="!pages.length">未定位具体页码，默认展示首页</p>
          </aside>

          <div
            class="search-preview-frame"
            :class="{ 'search-preview-frame--image': shouldScalePageImage }"
          >
            <img
              v-if="shouldScalePageImage"
              class="search-preview-image"
              :src="frameUrl"
              :alt="previewTitle"
            />
            <iframe v-else :src="frameUrl" :title="previewTitle" />
          </div>
        </div>
      </section>
    </div>
  </teleport>
</template>
