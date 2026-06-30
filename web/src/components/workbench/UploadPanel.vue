<script setup lang="ts">
import { ref } from 'vue'
import { useAnalyzeTask } from '../../composables/useAnalyzeTask'
import type { AnalyzeResponse } from '../../types/results'

const { submitting, task, error: submitError, start } = useAnalyzeTask()

const emit = defineEmits<{
  submitted: [payload: AnalyzeResponse]
}>()

const file = ref<File | null>(null)
const message = ref('')

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  file.value = input.files?.[0] || null
  message.value = ''
}

async function handleSubmit(e: Event) {
  e.preventDefault()
  if (!file.value) {
    message.value = '请选择图纸文件。'
    return
  }
  message.value = '正在提交识别任务...'
  const response = await start(file.value)
  if (response) {
    message.value = `任务已提交：${response.result_id}`
    emit('submitted', response)
  } else {
    message.value = submitError.value || '提交失败'
  }
}

defineExpose({ file, message })
</script>

<template>
  <form class="toolbar-upload toolbar-upload--dense" @submit="handleSubmit">
    <div class="toolbar-group toolbar-group--inputs">
      <label class="control control-file">
        <span class="control-file-icon" aria-hidden="true">⬆</span>
        <span>{{ file ? `输入 ${file.name}` : '输入 本地文件' }}</span>
        <input
          type="file"
          accept=".pdf,.png"
          @change="onFileChange"
          :disabled="submitting"
        />
      </label>
    </div>

    <div class="toolbar-group toolbar-group--actions">
      <button
        class="button primary"
        type="submit"
        :disabled="!file || submitting"
      >
        {{ submitting ? '提交中...' : '开始识别' }}
      </button>
    </div>
  </form>
  <p class="message" v-if="message" role="status">{{ message }}</p>
</template>
