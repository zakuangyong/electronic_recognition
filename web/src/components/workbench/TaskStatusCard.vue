<script setup lang="ts">
import { computed } from 'vue'
import type { ComponentData } from '../../types/results'

const props = defineProps<{
  components: ComponentData[]
  loading?: boolean
}>()

const aggregatedComponents = computed(() => {
  const groups = new Map<string, { code: string; label: string; count: number }>()

  for (const component of props.components) {
    const code = (component.code || component.reference_id || component.id || '').trim() || '--'
    const label = component.label || '未命名元件'
    const key = `${code}::${label}`
    const current = groups.get(key)
    if (current) {
      current.count += 1
      continue
    }
    groups.set(key, { code, label, count: 1 })
  }

  return Array.from(groups.values())
})
</script>

<template>
  <section class="panel result-summary-panel">
    <div class="panel-title panel-title--tight">
      <b>元件识别列表</b>
      <span class="label">components</span>
    </div>
    <div v-if="aggregatedComponents.length" class="component-list" role="list" aria-label="元件识别列表">
      <article
        v-for="component in aggregatedComponents"
        :key="`${component.code}-${component.label}`"
        class="component-list-item"
        role="listitem"
      >
        <div class="component-list-meta">
          <span class="component-list-kicker">元件代号</span>
          <strong :title="component.code" class="component-code-text">{{ component.code }}</strong>
          <span class="component-list-kicker">元件名称</span>
          <p :title="component.label">{{ component.label }}</p>
        </div>
        <div class="component-list-count">
          <span class="component-list-kicker">数量</span>
          <b>{{ component.count }}</b>
        </div>
      </article>
    </div>
    <div
      v-else-if="loading"
      class="preview-box component-list component-list-empty component-list-loading"
      role="status"
      aria-live="polite"
    >
      <div class="recognition-loader recognition-loader--compact" aria-hidden="true">
        <span></span>
        <span></span>
        <span></span>
      </div>
      <h3>识别中</h3>
      <p>正在汇总图纸内已定位的元件。</p>
      <div class="component-loading-stack" aria-hidden="true">
        <span></span>
        <span></span>
        <span></span>
      </div>
    </div>
    <div v-else class="preview-box empty-state component-list component-list-empty">
      <div class="drawing-placeholder">⌁</div>
      <h3>等待识别</h3>
      <p>识别完成后，这里列出已识别元件。</p>
    </div>
  </section>
</template>
