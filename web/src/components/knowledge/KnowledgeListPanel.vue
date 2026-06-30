<script setup lang="ts">
import { computed } from 'vue'
import type { ComponentItem, RuleItem } from '../../types/knowledge'

const props = defineProps<{
  components: ComponentItem[]
  rules: RuleItem[]
  activeKind: 'component' | 'rule'
  selectedId: string
  searchText: string
}>()

const emit = defineEmits<{
  select: [kind: 'component' | 'rule', id: string]
}>()

const items = computed(() => {
  const list = props.activeKind === 'component' ? props.components : props.rules
  const query = props.searchText.toLowerCase()
  if (!query) return list
  return list.filter((item: ComponentItem | RuleItem) => {
    const id = (item as ComponentItem).id || (item as RuleItem).id
    const name = (item as ComponentItem).label || (item as RuleItem).name || ''
    const type = props.activeKind === 'component'
      ? ((item as ComponentItem).component_type || '')
      : ((item as RuleItem).scope || '')
    return id.toLowerCase().includes(query) || name.toLowerCase().includes(query) || type.toLowerCase().includes(query)
  })
})

function getLabel(item: ComponentItem | RuleItem) {
  if (props.activeKind === 'component') return (item as ComponentItem).label || item.id
  return (item as RuleItem).name || item.id
}

function getSub(item: ComponentItem | RuleItem) {
  if (props.activeKind === 'component') {
    const ct = (item as ComponentItem)
    return ct.component_type || '未分类'
  }
  const r = item as RuleItem
  return `${r.scope || 'same_page'} · ${r.enabled ? '启用' : '停用'}`
}
</script>

<template>
  <div class="list-panel knowledge-tree-list">
    <div class="empty-editor" v-if="!items.length">
      <h3>暂无数据</h3>
      <p>可以点击右上角"新建"开始录入。</p>
    </div>
    <button
      v-for="item in items"
      :key="item.id"
      class="list-item tree-item"
      :class="{ active: item.id === selectedId }"
      type="button"
      @click="emit('select', activeKind, item.id)"
    >
      <strong>{{ getLabel(item) }}</strong>
      <span>{{ item.id }}</span>
      <span>{{ getSub(item) }}</span>
    </button>
  </div>
</template>
