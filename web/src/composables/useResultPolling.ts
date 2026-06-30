import { ref, onUnmounted } from 'vue'
import { getResult, getResultManifest, getResultSteps } from '../api/results'
import type { ResultDetail, ResultManifest, ResultSteps } from '../types/results'

export function useResultPolling() {
  const result = ref<ResultDetail | null>(null)
  const steps = ref<ResultSteps | null>(null)
  const manifest = ref<ResultManifest | null>(null)
  const loading = ref(false)
  const pollTimer = ref<ReturnType<typeof setInterval> | null>(null)

  function startPolling(resultId: string) {
    stopPolling()
    loading.value = true
    steps.value = null
    manifest.value = null
    poll(resultId)
    pollTimer.value = setInterval(() => poll(resultId), 2000)
  }

  async function poll(resultId: string) {
    try {
      const data = await getResult(resultId)
      result.value = data
      if (data.status === 'complete' || data.status === 'failed') {
        await Promise.allSettled([loadSteps(resultId), loadManifest(resultId)])
        stopPolling()
        loading.value = false
      } else {
        // Refresh the recognition log while the job is still running so the
        // workbench can stream live progress to the user.
        await loadSteps(resultId)
      }
    } catch {
      stopPolling()
      loading.value = false
    }
  }

  async function loadSteps(resultId: string) {
    try {
      steps.value = await getResultSteps(resultId)
    } catch {
      steps.value = null
    }
  }

  async function loadManifest(resultId: string) {
    try {
      manifest.value = await getResultManifest(resultId)
    } catch {
      manifest.value = null
    }
  }

  function stopPolling() {
    if (pollTimer.value) {
      clearInterval(pollTimer.value)
      pollTimer.value = null
    }
  }

  onUnmounted(() => {
    stopPolling()
  })

  return { result, steps, manifest, loading, startPolling, stopPolling, loadSteps, loadManifest }
}
