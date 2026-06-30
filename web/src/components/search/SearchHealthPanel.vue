<script setup lang="ts">
import type { HealthStatus } from '../../types/search'

defineProps<{
  status: HealthStatus | null
}>()

function modeLabel(value?: string) {
  const map: Record<string, string> = { bm25: 'BM25', vector: 'Vector', hybrid: 'Hybrid' }
  return map[value || ''] || value || '--'
}
</script>

<template>
  <details class="search-index-card" aria-labelledby="indexTitle">
    <summary class="preview-heading">
      <div>
        <p>INDEX</p>
        <h3 id="indexTitle">索引状态</h3>
      </div>
      <span class="preview-count">{{ modeLabel(status?.mode) }}</span>
    </summary>
    <dl class="search-stats">
      <div><dt>图纸</dt><dd>{{ status?.indexed_drawings ?? '--' }}</dd></div>
      <div><dt>Chunks</dt><dd>{{ status?.indexed_chunks ?? '--' }}</dd></div>
      <div><dt>向量点数</dt><dd>{{ status?.vector_points ?? '--' }}</dd></div>
      <div><dt>失败任务</dt><dd>{{ status?.failed_jobs ?? '--' }}</dd></div>
    </dl>
    <div class="health-grid">
      <article class="health-card">
        <span>SQLite</span>
        <strong>{{ status?.sqlite_available ? '可用' : '离线' }}</strong>
        <p>{{ status?.database ?? '索引数据库' }}</p>
      </article>
      <article class="health-card">
        <span>Embedding</span>
        <strong>{{ status?.embedding_backend_available ? '可用' : '未启用' }}</strong>
        <p>{{ status?.embedding_backend_available ? 'Embedding 后端已加载' : '当前未启用语义向量' }}</p>
      </article>
      <article class="health-card">
        <span>Qdrant</span>
        <strong>{{ status?.qdrant_available ? '可用' : '离线' }}</strong>
        <p>{{ status?.collection ? `${status.collection} · ${status.vector_points ?? 0} points` : '向量集合未初始化' }}</p>
      </article>
      <article class="health-card">
        <span>降级状态</span>
        <strong>{{ status?.degraded === false ? '完整' : '降级中' }}</strong>
        <p>{{ status?.degraded ? '当前使用 Exact + BM25 回退链路' : '当前链路支持混合检索' }}</p>
      </article>
    </div>
  </details>
</template>
