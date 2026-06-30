import { ref } from 'vue'
import { searchDrawings } from '../api/search'
import type { SearchQuery, SearchResponse, SearchResultItem } from '../types/search'

export function useSearch() {
  const loading = ref(false)
  const items = ref<SearchResultItem[]>([])
  const total = ref(0)
  const lastQuery = ref('')
  const retrievalMode = ref('')
  const degraded = ref(false)
  const degradedReason = ref('')
  const debugPayload = ref<Record<string, unknown>>({})
  let latestRequestId = 0

  async function submitSearch(payload: SearchQuery): Promise<SearchResponse | null> {
    const requestId = ++latestRequestId
    lastQuery.value = payload.query.trim()
    items.value = []
    total.value = 0
    loading.value = true
    try {
      const result = await searchDrawings(payload)
      if (requestId !== latestRequestId) return null
      items.value = result.items ?? []
      total.value = result.total ?? 0
      retrievalMode.value = result.retrieval_mode ?? ''
      degraded.value = result.degraded ?? false
      degradedReason.value = result.degraded_reason ?? ''
      debugPayload.value = result.query ?? {}
      return result
    } catch (error) {
      if (requestId !== latestRequestId) return null
      throw error
    } finally {
      if (requestId === latestRequestId) {
        loading.value = false
      }
    }
  }

  return { loading, items, total, lastQuery, retrievalMode, degraded, degradedReason, debugPayload, submitSearch }
}
