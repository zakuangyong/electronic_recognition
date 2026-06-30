<script setup lang="ts">
import { computed, ref } from 'vue'
import type { LogEntry } from '../../types/results'

const props = defineProps<{
  entries: LogEntry[]
  running?: boolean
  model?: string
}>()

const expanded = ref(false)

function formatMessage(entry: LogEntry | null) {
  if (!entry) return ''
  if (!props.model) return entry.message
  if (entry.message.includes(props.model)) return entry.message
  const isVisionCall = entry.stage === 'vision_model' || /准备调用视觉模型/.test(entry.message)
  if (!isVisionCall) return entry.message
  return `${entry.message}（模型：${props.model}）`
}

const latest = computed(() => (props.entries.length ? props.entries[props.entries.length - 1] : null))

// Newest first when expanded so the most recent progress is at the top.
const reversed = computed(() => [...props.entries].reverse())

function levelClass(level: string | undefined) {
  if (level === 'error') return 'error'
  if (level === 'warning') return 'warning'
  return 'info'
}

function formatTime(time: string | undefined) {
  if (!time) return ''
  const match = /T(\d{2}:\d{2}:\d{2})/.exec(time)
  return match ? match[1] : time
}

function toggle() {
  expanded.value = !expanded.value
}
</script>

<template>
  <section class="panel log-panel" :class="{ expanded }">
    <button type="button" class="log-panel-head" :aria-expanded="expanded" @click="toggle">
      <span class="log-dot" :class="levelClass(latest?.level)"></span>
      <span class="log-latest">
        {{ latest ? formatMessage(latest) : (running ? '识别任务进行中…' : '暂无日志') }}
      </span>
      <span class="log-panel-meta">
        <span v-if="entries.length" class="log-count">{{ entries.length }} 条</span>
        <span class="log-toggle">{{ expanded ? '收起' : '展开' }}</span>
        <span class="log-chevron" :class="{ open: expanded }">▾</span>
      </span>
    </button>

    <ol v-if="expanded" class="log-list" aria-label="识别任务日志">
      <li v-if="!entries.length" class="log-item log-item--empty">暂无历史日志。</li>
      <li v-for="(entry, index) in reversed" :key="index" class="log-item">
        <span class="log-dot" :class="levelClass(entry.level)"></span>
        <time class="log-time">{{ formatTime(entry.time) }}</time>
        <span class="log-message">{{ formatMessage(entry) }}</span>
      </li>
    </ol>
  </section>
</template>
