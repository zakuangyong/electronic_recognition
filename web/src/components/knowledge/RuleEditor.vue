<script setup lang="ts">
import { ref, watch } from 'vue'
import { uiCapabilities } from '../../app/uiCapabilities'
import type { RuleItem, RuleMember } from '../../types/knowledge'

const props = defineProps<{
  draft: RuleItem | null
}>()

const emit = defineEmits<{
  save: [payload: Record<string, unknown>]
  validate: [payload: Record<string, unknown>]
  test: [payload: { rule: Record<string, unknown>; detected_components: Array<Record<string, unknown>>; open_symbols: Array<Record<string, unknown>> }]
  invalid: [message: string]
  delete: []
}>()

const members = ref<RuleMember[]>([])
const detectedComponentsInput = ref('[]')
const openSymbolsInput = ref('[]')

watch(
  () => props.draft,
  (draft) => {
    members.value = draft?.members
      ? JSON.parse(JSON.stringify(draft.members))
      : []
    detectedComponentsInput.value = '[]'
    openSymbolsInput.value = '[]'
  },
  { immediate: true },
)

function splitList(value: string) {
  return value
    .split(/[,，]/g)
    .map((item) => item.trim())
    .filter(Boolean)
}

function updateMemberList(
  index: number,
  field: 'component_ids' | 'code_patterns' | 'label_keywords',
  value: string,
) {
  members.value[index][field] = splitList(value)
}

function buildPayload(form: HTMLFormElement) {
  const data = new FormData(form)
  return {
    id: data.get('id'),
    name: data.get('name'),
    description: data.get('description'),
    scope: data.get('scope'),
    confidence: parseFloat(String(data.get('confidence') || '0.95')),
    source: data.get('source'),
    notes: data.get('notes'),
    aliases: splitList(String(data.get('aliases') || '')),
    enabled: Boolean(data.get('enabled')),
    members: members.value,
  } satisfies Record<string, unknown>
}

function parseJsonArray(raw: string, fieldName: string) {
  const trimmed = raw.trim() || '[]'
  let parsed: unknown
  try {
    parsed = JSON.parse(trimmed)
  } catch {
    throw new Error(`${fieldName} 必须是 JSON 数组`)
  }
  if (!Array.isArray(parsed)) {
    throw new Error(`${fieldName} 必须是 JSON 数组`)
  }
  return parsed as Array<Record<string, unknown>>
}

function handleSubmit(e: Event) {
  e.preventDefault()
  const form = e.target as HTMLFormElement
  emit('save', buildPayload(form))
}

function addMember() {
  members.value.push({
    role: '',
    min_quantity: 1,
    component_ids: [],
    code_patterns: [],
    label_keywords: [],
  })
}

function removeMember(index: number) {
  members.value.splice(index, 1)
}

function handleValidate(form: HTMLFormElement) {
  emit('validate', buildPayload(form))
}

function handleTest(form: HTMLFormElement) {
  try {
    emit('test', {
      rule: buildPayload(form),
      detected_components: parseJsonArray(detectedComponentsInput.value, 'detected_components'),
      open_symbols: parseJsonArray(openSymbolsInput.value, 'open_symbols'),
    })
  } catch (error) {
    emit('invalid', error instanceof Error ? error.message : '试运行样本格式不合法')
  }
}
</script>

<template>
  <form class="editor-form editor-form--flat" data-form="rule" @submit="handleSubmit" v-if="draft">
    <section class="form-section form-section--flat">
      <div class="section-heading">
        <p>BASIC</p>
        <h3>组合元件信息</h3>
      </div>
      <div class="field-grid">
        <label><span>ID</span><input name="id" required :value="draft.id" /></label>
        <label><span>名称</span><input name="name" required :value="draft.name" /></label>
        <label><span>作用域</span>
          <select name="scope" :value="draft.scope">
            <option value="same_page">same_page</option>
            <option value="document">document</option>
          </select>
        </label>
        <label><span>默认置信度</span><input name="confidence" type="number" min="0" max="1" step="0.01" :value="draft.confidence" /></label>
        <label><span>来源</span><input name="source" :value="draft.source" /></label>
        <label class="full"><span>描述</span><textarea name="description" rows="3" :value="draft.description"></textarea></label>
        <label><span>别名</span><input name="aliases" :value="draft.aliases?.join(', ')" placeholder="逗号分隔" /></label>
        <label class="full"><span>备注</span><textarea name="notes" rows="3" :value="draft.notes"></textarea></label>
      </div>
      <label class="toggle-field"><input type="checkbox" name="enabled" :checked="draft.enabled !== false" />启用该组合元件</label>
    </section>

    <section class="form-section form-section--flat">
      <div class="section-heading">
        <p>MEMBERS</p>
        <h3>成员编排</h3>
      </div>
      <div class="member-toolbar">
        <button class="ghost-button" type="button" @click="addMember">添加成员</button>
      </div>
      <div class="member-list">
        <article v-for="(member, index) in members" :key="index" class="member-card">
          <div class="member-card-header">
            <strong>成员 {{ index + 1 }}</strong>
            <button class="danger-button subtle" type="button" @click="removeMember(index)">删除</button>
          </div>
          <div class="field-grid">
            <label><span>角色</span><input v-model="member.role" /></label>
            <label><span>最小数量</span><input v-model.number="member.min_quantity" type="number" min="1" /></label>
            <label class="full">
              <span>组件 ID</span>
              <input
                :value="member.component_ids.join(', ')"
                placeholder="例如 KM1, KA1"
                @input="updateMemberList(index, 'component_ids', ($event.target as HTMLInputElement).value)"
              />
            </label>
            <label class="full">
              <span>编码模式</span>
              <input
                :value="member.code_patterns.join(', ')"
                placeholder="正则，逗号分隔"
                @input="updateMemberList(index, 'code_patterns', ($event.target as HTMLInputElement).value)"
              />
            </label>
            <label class="full">
              <span>标签关键词</span>
              <input
                :value="member.label_keywords.join(', ')"
                placeholder="关键词，逗号分隔"
                @input="updateMemberList(index, 'label_keywords', ($event.target as HTMLInputElement).value)"
              />
            </label>
          </div>
        </article>
        <div v-if="!members.length" class="empty-editor">
          <p>暂无成员，点击"添加成员"开始编排。</p>
        </div>
      </div>
    </section>

    <section class="form-section form-section--flat">
      <div class="section-heading">
        <p>TEST</p>
        <h3>试运行结果</h3>
      </div>
      <div class="field-grid">
        <label class="full">
          <span>detected_components</span>
          <textarea v-model="detectedComponentsInput" rows="4" placeholder='例如 [{"component_type":"relay","page":1}]'></textarea>
        </label>
        <label class="full">
          <span>open_symbols</span>
          <textarea v-model="openSymbolsInput" rows="4" placeholder='例如 [{"label":"KM1","page":1}]'></textarea>
        </label>
      </div>
      <div class="member-toolbar">
        <button class="ghost-button" data-action="validate-rule" type="button" @click="handleValidate(($event.currentTarget as HTMLButtonElement).form!)">校验规则</button>
        <button class="secondary-button" data-action="test-rule" type="button" @click="handleTest(($event.currentTarget as HTMLButtonElement).form!)">试运行</button>
        <button
          class="secondary-button"
          type="button"
          data-capability="compare-version"
          :disabled="!uiCapabilities.knowledge.compareVersion"
        >
          版本对比
        </button>
      </div>
    </section>

  </form>

  <div class="empty-editor" v-else>
    <h3>选择左侧记录查看详情</h3>
    <p>组合元件支持成员编排和精确组件选择。</p>
  </div>
</template>
