import { ref } from 'vue'
import { submitAnalyze } from '../api/results'
import type { AnalyzeResponse } from '../types/results'

export function useAnalyzeTask() {
  const submitting = ref(false)
  const task = ref<AnalyzeResponse | null>(null)
  const error = ref('')

  async function start(file: File) {
    submitting.value = true
    error.value = ''
    task.value = null
    try {
      task.value = await submitAnalyze(file)
      return task.value
    } catch (err) {
      error.value = err instanceof Error ? err.message : '提交失败'
      return null
    } finally {
      submitting.value = false
    }
  }

  return { submitting, task, error, start }
}
