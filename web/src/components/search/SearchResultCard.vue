<script setup lang="ts">
import type { SearchResultItem } from '../../types/search'

defineProps<{
  item: SearchResultItem
  index: number
}>()

const emit = defineEmits<{
  (e: 'select'): void
  (e: 'open-preview'): void
}>()

function chunkTypeReason(value: string) {
  const normalized = value.trim().toLowerCase()
  if (!normalized) return ''
  if (normalized === 'drawing') return '命中图纸页'
  if (normalized === 'component_table') return '命中元件表'
  if (normalized === 'combination') return '命中组合规则'
  return `命中 ${value}`
}

type EvidenceTag = {
  label: string
  tone: 'blue' | 'green'
  priority: number
}

function hitReason(item: SearchResultItem) {
  const parts: string[] = []
  if (item.matched_components?.length) {
    parts.push(`精确命中 ${item.matched_components.slice(0, 2).join(' / ')}`)
  }
  if (item.matched_combinations?.length) {
    parts.push(`命中 ${item.matched_combinations[0]}`)
  }
  if (item.match_sources?.includes('bm25')) {
    parts.push('关键词命中')
  }
  if (item.match_sources?.includes('dense') || item.match_sources?.includes('vector')) {
    parts.push('包含语义命中')
  }
  for (const chunkType of item.matched_chunk_types || []) {
    const reason = chunkTypeReason(chunkType)
    if (reason) parts.push(reason)
  }
  return Array.from(new Set(parts)).join('，') || '命中摘要与页码信息'
}

function evidenceTags(item: SearchResultItem) {
  const tags: EvidenceTag[] = []

  for (const component of item.matched_components.slice(0, 2)) {
    tags.push({ label: component, tone: 'blue', priority: 10 })
  }
  for (const combination of item.matched_combinations.slice(0, 1)) {
    tags.push({ label: combination, tone: 'green', priority: 20 })
  }
  if (item.match_sources?.includes('bm25')) {
    tags.push({ label: '关键词命中', tone: 'blue', priority: 30 })
  }
  if (item.match_sources?.includes('dense') || item.match_sources?.includes('vector')) {
    tags.push({ label: '包含语义命中', tone: 'green', priority: 40 })
  }
  for (const chunkType of item.matched_chunk_types || []) {
    const label = chunkTypeReason(chunkType)
    if (!label) continue
    tags.push({ label, tone: 'green', priority: 50 })
  }
  for (const page of item.matched_pages.slice(0, 3)) {
    tags.push({ label: `命中页 ${page}`, tone: 'blue', priority: 60 })
  }

  const deduped = Array.from(
    new Map(tags.map((tag) => [tag.label, tag])).values(),
  )

  return deduped
    .sort((left, right) => left.priority - right.priority || left.label.localeCompare(right.label))
    .slice(0, 5)
}
</script>

<template>
  <article class="search-result-item search-result-item--stream" @click="emit('select')">
    <div class="search-result-main">
      <header class="search-result-head">
        <span class="result-rank">{{ index + 1 }}</span>
        <div class="result-head-copy">
          <h3>{{ item.drawing_title || item.filename || item.result_id }}</h3>
          <p>
            {{
              [
                item.drawing_number,
                item.revision && `修订 ${item.revision}`,
                item.project_name || item.system_name,
              ]
                .filter(Boolean)
                .join(' · ')
            }}
          </p>
        </div>
      </header>

      <p class="result-snippet">{{ item.snippet || '暂无命中摘要' }}</p>
      <div class="result-why">
        <b>命中理由</b>
        <span>{{ hitReason(item) }}</span>
      </div>

      <div class="search-tags">
        <span
          v-for="tag in evidenceTags(item)"
          :key="tag.label"
          class="search-tag"
          :class="tag.tone"
        >
          {{ tag.label }}
        </span>
      </div>

      <div class="search-result-meta">
        <span>命中证据 {{ item.matched_pages.length || 0 }} 处</span>
        <span v-if="item.collapsed_versions > 0">
          已折叠 {{ item.collapsed_versions }} 个历史版本
        </span>
      </div>
    </div>

    <aside class="search-result-actions">
      <button
        type="button"
        class="result-action result-action--primary"
        data-action="open-preview"
        @click="emit('open-preview')"
      >
        打开图纸
      </button>
      <button type="button" class="result-action" disabled aria-disabled="true">定位命中页</button>
      <button type="button" class="result-action" disabled aria-disabled="true">展开命中</button>
    </aside>
  </article>
</template>
