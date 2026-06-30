import { ref } from 'vue'
import { getResult } from '../api/results'
import type { ResultDetail } from '../types/results'

export function useResultLoader() {
  const result = ref<ResultDetail | null>(null)
  const loading = ref(false)
  const error = ref('')

  async function load(resultId: string) {
    loading.value = true
    error.value = ''
    result.value = null
    try {
      result.value = await getResult(resultId)
    } catch (err) {
      error.value = err instanceof Error ? err.message : '获取结果失败'
    } finally {
      loading.value = false
    }
  }

  return { result, loading, error, load }
}
