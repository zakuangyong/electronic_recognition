<script setup lang="ts">
import { computed, ref, watchEffect } from 'vue'
import type { DiffItem } from '../../types/diff'

const props = defineProps<{
  items: DiffItem[]
  activeId: string | null
  page: number
}>()

const emit = defineEmits<{
  (e: 'select', id: string): void
  (e: 'visibleIds', ids: string[]): void
}>()

type ChangeFilter = 'all' | 'graphic_or_text' | 'text_changed' | 'visual_change'

const query = ref('')
const filter = ref<ChangeFilter>('all')

const filteredItems = computed(() => {
  const q = query.value.trim().toLowerCase()
  return props.items.filter((item) => {
    if (filter.value !== 'all' && item.changed_type !== filter.value) return false
    if (!q) return true
    const hay = [
      item.id,
      String(item.page),
      item.changed_type,
      item.old_text || '',
      item.new_text || '',
    ]
      .join(' ')
      .toLowerCase()
    return hay.includes(q)
  })
})

watchEffect(() => {
  emit(
    'visibleIds',
    filteredItems.value.map((item) => item.id),
  )
})

function pick(id: string) {
  emit('select', id)
}

function isActive(id: string) {
  return props.activeId === id
}

function changeLabel(value: string) {
  const map: Record<string, string> = {
    text_changed: '文本变化',
    visual_change: '图形变化',
    graphic_or_text: '图文变化',
  }
  return map[value] || value
}
</script>

<template>
  <section class="diff-a-panel diff-a-panel--items" data-testid="diff-items-panel">
    <header class="diff-a-panelHeader">
      <div class="diff-a-h">
        <b>差异清单</b>
        <span>click to focus · filter · search</span>
      </div>
      <span class="diff-a-tag">items</span>
    </header>

    <div class="diff-a-panelBody diff-a-items">
      <div class="diff-a-searchRow">
        <input
          v-model="query"
          class="diff-a-search"
          type="search"
          placeholder="搜索：ID / 文本 / 页码 / 类型"
          :aria-label="`搜索第 ${page} 页差异`"
        />
        <div class="diff-a-count" data-testid="diff-items-count">
          {{ filteredItems.length }}
        </div>
      </div>

      <div class="diff-a-filterRow" role="tablist" aria-label="差异类型筛选">
        <button
          class="diff-a-fchip"
          :class="{ on: filter === 'all' }"
          type="button"
          @click="filter = 'all'"
        >
          全部
        </button>
        <button
          class="diff-a-fchip"
          :class="{ on: filter === 'graphic_or_text' }"
          data-type="graphic_or_text"
          type="button"
          @click="filter = 'graphic_or_text'"
        >
          图文变化
        </button>
        <button
          class="diff-a-fchip"
          :class="{ on: filter === 'text_changed' }"
          data-type="text_changed"
          type="button"
          @click="filter = 'text_changed'"
        >
          文本变化
        </button>
        <button
          class="diff-a-fchip"
          :class="{ on: filter === 'visual_change' }"
          data-type="visual_change"
          type="button"
          @click="filter = 'visual_change'"
        >
          图形变化
        </button>
      </div>

      <div class="diff-a-itemList" role="list">
        <button
          v-for="item in filteredItems"
          :key="item.id"
          class="diff-a-item"
          :class="{ active: isActive(item.id) }"
          type="button"
          role="listitem"
          :data-testid="`diff-item-${item.id}`"
          @click="pick(item.id)"
        >
          <div class="diff-a-itemTop">
            <div class="diff-a-itemLeft">
              <div class="diff-a-itemId">{{ item.id }}</div>
              <div class="diff-a-itemSub">
                <span>page {{ item.page }}</span>
                <span>{{ changeLabel(item.changed_type) }}</span>
              </div>
            </div>
            <div class="diff-a-typeMark" :data-type="item.changed_type"></div>
          </div>

          <div class="diff-a-itemMid">
            <div class="diff-a-thumb">
              <img v-if="item.crop_image_url" :src="item.crop_image_url" alt="差异区域" />
              <span v-else class="diff-a-thumbEmpty">—</span>
            </div>
            <div class="diff-a-pair">
              <div class="diff-a-pairRow">
                <div class="diff-a-k">old</div>
                <div class="diff-a-v" :class="{ muted: !item.old_text }">
                  {{ item.old_text || '—' }}
                </div>
              </div>
              <div class="diff-a-pairRow">
                <div class="diff-a-k">new</div>
                <div class="diff-a-v" :class="{ muted: !item.new_text }">
                  {{ item.new_text || '—' }}
                </div>
              </div>
            </div>
          </div>
        </button>
      </div>
    </div>
  </section>
</template>
