<script setup lang="ts">
import { nextTick, ref } from 'vue'
import type { SearchQuery } from '../../types/search'

defineProps<{
  loading: boolean
}>()

const query = ref('')
// 检索方式固定为 BM25：后端默认 search_mode=bm25，前端不再暴露可选项。
const mode = ref('bm25')
const rebuildMode = ref('all')
const queryInput = ref<HTMLInputElement | null>(null)

const quickTags = [
  '热继驱动',
  '三极断路器',
  '接触器',
  '热继保护',
  '端子排',
  '风机启动',
] as const

const emit = defineEmits<{
  search: [payload: SearchQuery]
  rebuild: [mode: string]
}>()

function handleSubmit(e: Event) {
  e.preventDefault()
  const q = query.value.trim()
  if (!q) return
  emit('search', {
    query: q,
    limit: 20,
    retrieval_mode: mode.value,
  })
}

function handleRebuild() {
  emit('rebuild', rebuildMode.value)
}

function submitSearch() {
  const q = query.value.trim()
  if (!q) return
  emit('search', {
    query: q,
    limit: 20,
    retrieval_mode: mode.value,
  })
}

async function applyQuickTag(text: string) {
  query.value = text
  await nextTick()
  queryInput.value?.focus()
}

defineExpose({ query, mode, rebuildMode, submitSearch, handleRebuild })
</script>

<template>
  <div class="search-toolbar-card panel search-toolbar-card--flat" aria-labelledby="searchTitle">
    <div class="panel-title panel-title--tight">
      <b id="searchTitle">检索条件</b>
      <span class="label">查询输入</span>
    </div>
    <form class="search-form search-form--flat" @submit="handleSubmit">
      <label>
        <span>关键词、图号、合同号或元件代号</span>
        <input
          ref="queryInput"
          v-model="query"
          type="search"
          autocomplete="off"
          placeholder="例如 A17387_1706、KM1、带热继保护的风机启动图"
        />
      </label>
      <div class="search-quick">
        <span class="search-quick-title">快捷输入</span>
        <div class="search-quick-tags" role="list" aria-label="快捷输入标签">
          <button
            v-for="tag in quickTags"
            :key="tag"
            type="button"
            class="diff-a-chip"
            role="listitem"
            @click="applyQuickTag(tag)"
          >
            {{ tag }}
          </button>
        </div>
      </div>
    </form>
  </div>
</template>
