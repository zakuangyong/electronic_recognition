import { ref } from 'vue'
import { fetchSearchHealth } from '../api/search'
import type { HealthStatus } from '../types/search'

export function useSearchHealth() {
  const loading = ref(false)
  const status = ref<HealthStatus | null>(null)
  const error = ref('')

  async function refresh() {
    loading.value = true
    error.value = ''
    try {
      status.value = await fetchSearchHealth()
    } catch (err) {
      error.value = err instanceof Error ? err.message : '连接失败'
      status.value = null
    } finally {
      loading.value = false
    }
  }

  return { loading, status, error, refresh }
}
