<script setup lang="ts">
import type { ComponentItem } from '../../types/knowledge'

const props = defineProps<{
  draft: ComponentItem | null
}>()

const emit = defineEmits<{
  save: [payload: Record<string, unknown>]
  delete: []
}>()

function handleSubmit(e: Event) {
  e.preventDefault()
  const form = e.target as HTMLFormElement
  const data = new FormData(form)
  const payload: Record<string, unknown> = {
    id: data.get('id'),
    label: data.get('label'),
    component_type: data.get('component_type'),
    model: data.get('model'),
    definition: data.get('definition'),
    standards: String(data.get('standards') || '').split(/[,，]/g).map(s => s.trim()).filter(Boolean),
    aliases: String(data.get('aliases') || '').split(/[,，]/g).map(s => s.trim()).filter(Boolean),
    source: data.get('source'),
    notes: data.get('notes'),
    enabled: Boolean(data.get('enabled')),
  }
  emit('save', payload)
}

</script>

<template>
  <form class="editor-form editor-form--flat" data-form="component" @submit="handleSubmit" v-if="draft">
    <section class="form-section form-section--flat">
      <div class="section-heading">
        <p>BASIC</p>
        <h3>单元件信息</h3>
      </div>
      <div class="field-grid">
        <label><span>ID</span><input name="id" required :value="draft.id" /></label>
        <label><span>名称</span><input name="label" required :value="draft.label" /></label>
        <label><span>元件类型</span><input name="component_type" :value="draft.component_type" /></label>
        <label><span>型号</span><input name="model" :value="draft.model" /></label>
        <label class="full"><span>定义</span><textarea name="definition" rows="3" :value="draft.definition"></textarea></label>
        <label><span>标准</span><input name="standards" :value="draft.standards?.join(', ')" placeholder="逗号分隔" /></label>
        <label><span>别名</span><input name="aliases" :value="draft.aliases?.join(', ')" placeholder="逗号分隔" /></label>
        <label><span>来源</span><input name="source" :value="draft.source" /></label>
        <label class="full"><span>备注</span><textarea name="notes" rows="3" :value="draft.notes"></textarea></label>
      </div>
      <label class="toggle-field"><input type="checkbox" name="enabled" :checked="draft.enabled !== false" />启用该单元件</label>
    </section>
  </form>

  <div class="empty-editor" v-else>
    <h3>选择左侧记录查看详情</h3>
    <p>单元件支持图片维护。</p>
  </div>
</template>
