<script setup lang="ts">
import type { SearchResultItem } from '../../types/search'
import SearchResultCard from './SearchResultCard.vue'

defineProps<{
  items: SearchResultItem[]
  total: number
  query: string
  retrievalMode: string
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'select', item: SearchResultItem): void
  (e: 'open-preview', item: SearchResultItem): void
}>()
</script>

<template>
  <section class="search-results-panel search-results-panel--stream" aria-labelledby="resultsTitle">
    <div class="search-results-summary">
      <div class="summary-main">
        <b id="resultsTitle">查询结果</b>
        <span v-if="query">查询：{{ query }}</span>
        <span>找到 {{ total }} 条结果</span>
        <span>排序：相关度优先</span>
      </div>
      <div class="summary-filters">
        <span class="summary-chip summary-chip--active">全部结果</span>
        <span class="summary-chip">精确命中优先</span>
        <span class="summary-chip">语义命中优先</span>
        <span class="summary-chip">模式 {{ retrievalMode || 'bm25' }}</span>
      </div>
    </div>

    <section class="panel">
      <div class="search-empty" v-if="!items.length">
        <template v-if="loading">
          <h3>正在检索</h3>
          <p>正在根据当前查询条件拉取结果，请稍候查看命中图纸与摘要。</p>
        </template>
        <template v-else-if="query">
          <h3>未找到匹配结果</h3>
          <p>可以尝试缩短关键词、切换检索模式，或改用图号、元件代号和项目名称开始检索。</p>
        </template>
        <template v-else>
          <h3>等待检索</h3>
          <p>输入图号、元件代号、型号或功能描述后，结果会按图纸聚合并展示命中来源。</p>
        </template>
      </div>
      <div class="search-result-list" v-else>
        <SearchResultCard
          v-for="(item, index) in items"
          :key="item.drawing_id"
          :item="item"
          :index="index"
          @select="emit('select', item)"
          @open-preview="emit('open-preview', item)"
        />
      </div>
    </section>
  </section>
</template>
