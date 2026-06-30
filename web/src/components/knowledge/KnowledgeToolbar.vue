<script setup lang="ts">
defineProps<{
  activeKind: 'component' | 'rule'
}>()

const emit = defineEmits<{
  'update:activeKind': [kind: 'component' | 'rule']
  create: []
  refresh: []
}>()
</script>

<template>
  <div class="sidebar-toolbar scheme-c-toolbar-strip">
    <div class="kind-switch" role="tablist" aria-label="知识库类型">
      <button
        class="kind-tab"
        :class="{ active: activeKind === 'component' }"
        type="button"
        @click="emit('update:activeKind', 'component')"
      >单元件</button>
      <button
        class="kind-tab"
        :class="{ active: activeKind === 'rule' }"
        type="button"
        @click="emit('update:activeKind', 'rule')"
      >组合元件</button>
    </div>
    <div class="toolbar-actions">
      <button class="ghost-button" type="button" @click="emit('refresh')">刷新</button>
      <button class="primary-button" type="button" @click="emit('create')">新建</button>
    </div>
  </div>
</template>
