<script setup lang="ts">
import { ref } from 'vue'
import { fetchDemoQueries } from '../../api/search'
import type { DemoQueryGroup, DemoQueryItem } from '../../types/search'

const props = defineProps<{
  onQueryClick: (query: string) => void
}>()

const groups = ref<DemoQueryGroup>({})
const count = ref(0)

async function load() {
  try {
    groups.value = await fetchDemoQueries()
    count.value = Object.keys(groups.value).length
  } catch {
    groups.value = {}
    count.value = 0
  }
}

function groupLabel(type: string) {
  const map: Record<string, string> = {
    exact: '精确检索',
    keyword: '关键词检索',
    semantic: '语义检索',
    constraint: '组合约束',
  }
  return map[type] || type
}

function entries() {
  return Object.entries(groups.value).filter(
    ([, items]) => Array.isArray(items) && items.length > 0,
  )
}

function esc(value: unknown) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

defineExpose({ load })
</script>

<template>
  <details class="search-index-card" aria-labelledby="demoTitle">
    <summary class="preview-heading">
      <div>
        <p>DEMO</p>
        <h3 id="demoTitle">演示查询集</h3>
      </div>
      <span class="preview-count">{{ count }} 组</span>
    </summary>
    <div class="demo-query-groups" v-if="count">
      <section v-for="[type, items] in entries()" :key="type" class="demo-query-group">
        <h4>{{ esc(groupLabel(type)) }}</h4>
        <div class="demo-query-list">
          <button
            v-for="item in items"
            :key="item.query"
            class="demo-query-item"
            type="button"
            :title="item.notes || ''"
            @click="props.onQueryClick(item.query)"
          >
            <strong>{{ esc(item.query) }}</strong>
            <span>{{ esc(item.notes || '') }}</span>
          </button>
        </div>
      </section>
    </div>
    <p class="demo-tip" v-else>
      点击任一查询可自动填入检索框，并保留当前模式进行对照演示。
    </p>
  </details>
</template>
