<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import KnowledgeToolbar from '../components/knowledge/KnowledgeToolbar.vue'
import KnowledgeListPanel from '../components/knowledge/KnowledgeListPanel.vue'
import ComponentEditor from '../components/knowledge/ComponentEditor.vue'
import RuleEditor from '../components/knowledge/RuleEditor.vue'
import {
  createComponent,
  createRule,
  deleteComponent,
  deleteRule,
  fetchCustomRules,
  fetchKnowledge,
  getComponent,
  getRule,
  updateComponent,
  updateRule,
  uploadComponentImage,
  uploadRuleImage,
  validateRule,
  testRule,
} from '../api/knowledge'
import type { ComponentItem, RuleItem } from '../types/knowledge'

import '../app/styles/knowledge.css'
import '../app/styles/diff.css'

type Kind = 'component' | 'rule'
type Message = { type: 'success' | 'error' | 'info'; text: string }

const activeKind = ref<Kind>('component')
const searchText = ref('')
const selectedId = ref('')
const editorHost = ref<HTMLElement | null>(null)

const components = ref<ComponentItem[]>([])
const rules = ref<RuleItem[]>([])
const loadingCatalog = ref(false)

const componentDraft = ref<ComponentItem | null>(null)
const ruleDraft = ref<RuleItem | null>(null)
const loadingEditor = ref(false)

const message = ref<Message | null>(null)

const componentTotal = computed(() => components.value.length)
const ruleTotal = computed(() => rules.value.length)
const componentEnabled = computed(() => components.value.filter(item => item.enabled !== false).length)
const ruleEnabled = computed(() => rules.value.filter(item => item.enabled !== false).length)

const editorTitle = computed(() => {
  if (activeKind.value === 'component') return componentDraft.value?.label || componentDraft.value?.id || '单元件详情'
  return ruleDraft.value?.name || ruleDraft.value?.id || '组合元件详情'
})
const scopeLabel = computed(() => ruleDraft.value?.scope || 'same_page')
const confidenceLabel = computed(() => {
  if (activeKind.value !== 'rule') return '组件模式'
  return `阈值 ${Number(ruleDraft.value?.confidence || 0.95).toFixed(2)}`
})

function handleComponentImageUpload(e: Event, kind: string) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) handleUploadComponent(file, kind)
}

function handleRuleImageUpload(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) handleUploadRule(file)
}

function setMessage(type: Message['type'], text: string) {
  message.value = { type, text }
}

function handleInvalidRuleInput(text: string) {
  setMessage('error', text)
}

function clearEditor() {
  selectedId.value = ''
  componentDraft.value = null
  ruleDraft.value = null
}

async function refreshCatalog() {
  loadingCatalog.value = true
  message.value = null
  try {
    const [componentResp, ruleResp] = await Promise.all([
      fetchKnowledge(),
      fetchCustomRules(),
    ])
    components.value = componentResp.items
    rules.value = ruleResp.items
  } catch (err) {
    setMessage('error', err instanceof Error ? err.message : '知识库加载失败')
  } finally {
    loadingCatalog.value = false
  }
}

function newComponentDraft(): ComponentItem {
  return {
    id: '',
    label: '',
    image_path: '',
    image_url: '',
    variant_images: [],
    variant_image_urls: [],
    component_type: '',
    model: '',
    definition: '',
    standards: [],
    aliases: [],
    notes: '',
    source: '',
    enabled: true,
    created_at: '',
    updated_at: '',
  }
}

function newRuleDraft(): RuleItem {
  return {
    id: '',
    name: '',
    description: '',
    image_path: '',
    image_url: '',
    engine: '',
    enabled: true,
    scope: 'same_page',
    confidence: 0.95,
    aliases: [],
    notes: '',
    source: '',
    member_count: 0,
    members: [],
    created_at: '',
    updated_at: '',
  }
}

async function handleCreate() {
  message.value = null
  selectedId.value = ''
  if (activeKind.value === 'component') {
    componentDraft.value = newComponentDraft()
    ruleDraft.value = null
    return
  }
  ruleDraft.value = newRuleDraft()
  componentDraft.value = null
}

async function handleSelect(kind: Kind, id: string) {
  activeKind.value = kind
  selectedId.value = id
  message.value = null
  loadingEditor.value = true
  try {
    if (kind === 'component') {
      ruleDraft.value = null
      componentDraft.value = await getComponent(id)
    } else {
      componentDraft.value = null
      ruleDraft.value = await getRule(id)
    }
  } catch (err) {
    setMessage('error', err instanceof Error ? err.message : '加载详情失败')
    clearEditor()
  } finally {
    loadingEditor.value = false
  }
}

async function handleSaveComponent(payload: Record<string, unknown>) {
  message.value = null
  try {
    const currentId = selectedId.value
    const saved = currentId
      ? await updateComponent(currentId, payload)
      : await createComponent(payload)
    componentDraft.value = saved
    selectedId.value = saved.id
    activeKind.value = 'component'
    await refreshCatalog()
    setMessage('success', '单元件已保存')
  } catch (err) {
    setMessage('error', err instanceof Error ? err.message : '保存失败')
  }
}

async function handleSaveRule(payload: Record<string, unknown>) {
  message.value = null
  try {
    const currentId = selectedId.value
    const saved = currentId ? await updateRule(currentId, payload) : await createRule(payload)
    ruleDraft.value = saved
    selectedId.value = saved.id
    activeKind.value = 'rule'
    await refreshCatalog()
    setMessage('success', '组合元件已保存')
  } catch (err) {
    setMessage('error', err instanceof Error ? err.message : '保存失败')
  }
}

async function handleDeleteActive() {
  message.value = null
  const id = selectedId.value
  if (!id) {
    setMessage('info', '请先选择一条记录')
    return
  }
  try {
    if (activeKind.value === 'component') {
      await deleteComponent(id)
    } else {
      await deleteRule(id)
    }
    clearEditor()
    await refreshCatalog()
    setMessage('success', '已删除')
  } catch (err) {
    setMessage('error', err instanceof Error ? err.message : '删除失败')
  }
}

async function handleUploadComponent(file: File, kind: string) {
  message.value = null
  const id = selectedId.value
  if (!id) {
    setMessage('info', '请先保存该单元件，再上传图片')
    return
  }
  try {
    const updated = await uploadComponentImage(id, file, file.name, kind)
    componentDraft.value = updated
    await refreshCatalog()
    setMessage('success', '图片已上传')
  } catch (err) {
    setMessage('error', err instanceof Error ? err.message : '图片上传失败')
  }
}

async function handleUploadRule(file: File) {
  message.value = null
  const id = selectedId.value
  if (!id) {
    setMessage('info', '请先保存该组合元件，再上传图片')
    return
  }
  try {
    const updated = await uploadRuleImage(id, file, file.name)
    ruleDraft.value = updated
    await refreshCatalog()
    setMessage('success', '图片已上传')
  } catch (err) {
    setMessage('error', err instanceof Error ? err.message : '图片上传失败')
  }
}

async function handleValidateRule(payload: Record<string, unknown>) {
  message.value = null
  try {
    const result = await validateRule(payload)
    if (result.valid) {
      const memberCount = Number((result.summary || {}).member_count || 0)
      setMessage('success', `规则校验通过，成员数 ${memberCount}`)
      return
    }
    setMessage('error', '规则校验未通过')
  } catch (err) {
    setMessage('error', err instanceof Error ? err.message : '规则校验失败')
  }
}

async function handleTestRule(payload: {
  rule: Record<string, unknown>
  detected_components: Array<Record<string, unknown>>
  open_symbols: Array<Record<string, unknown>>
}) {
  message.value = null
  try {
    const result = await testRule(payload)
    setMessage('success', `试运行命中 ${result.matches.length} 条结果`)
  } catch (err) {
    setMessage('error', err instanceof Error ? err.message : '规则试运行失败')
  }
}

function submitActiveEditor() {
  const selector = activeKind.value === 'component' ? 'form[data-form="component"]' : 'form[data-form="rule"]'
  const form = editorHost.value?.querySelector(selector) as HTMLFormElement | null
  form?.requestSubmit()
}

function triggerEditorAction(selector: string) {
  const button = editorHost.value?.querySelector(selector) as HTMLButtonElement | null
  button?.click()
}

onMounted(async () => {
  await refreshCatalog()
})
</script>

<template>
  <div class="diff-a-root">
    <div class="topbar topbar--dark">
      <div>
        <h1>知识库管理</h1>
        <p>KNOWLEDGE · CATALOG → EDIT → TEST</p>
      </div>
      <div class="chips">
        <RouterLink class="chip" to="/workbench">识别工作台</RouterLink>
        <RouterLink class="chip" to="/search">图纸检索</RouterLink>
        <RouterLink class="chip" to="/drawing-diff">图纸比对</RouterLink>
        <RouterLink class="chip active" to="/knowledge">知识库管理</RouterLink>
      </div>
    </div>

    <section class="diff-a-shell">
      <header class="diff-a-topbar">
        <div class="diff-a-meta">
          <span class="diff-a-pill">
            <span class="diff-a-dot"></span>
            <b>组件 {{ componentTotal }}</b>
            <span>enabled {{ componentEnabled }}</span>
          </span>
          <span class="diff-a-pill">
            <span class="diff-a-dot"></span>
            <b>规则 {{ ruleTotal }}</b>
            <span>enabled {{ ruleEnabled }}</span>
          </span>
          <span class="diff-a-pill">
            <span class="diff-a-dot"></span>
            <b>{{ activeKind === 'component' ? '单元件' : '组合元件' }}</b>
            <span>{{ activeKind === 'rule' ? scopeLabel : 'component' }}</span>
          </span>
          <span class="diff-a-pill">
            <span class="diff-a-dot"></span>
            <b>{{ selectedId || '--' }}</b>
            <span>current</span>
          </span>
          <span class="diff-a-pill">
            <span class="diff-a-dot"></span>
            <b>{{ confidenceLabel }}</b>
            <span>confidence</span>
          </span>
        </div>
        <div class="diff-a-actions">
          <button class="diff-a-chip" type="button" @click="refreshCatalog">刷新目录</button>
          <button class="diff-a-chip diff-a-chip--primary" type="button" @click="submitActiveEditor">
            保存
          </button>
          <button
            class="diff-a-chip"
            type="button"
            @click="triggerEditorAction('[data-action=&quot;test-rule&quot;]')"
          >
            试运行
          </button>
          <button class="diff-a-chip" type="button" data-capability="compare-version" disabled>
            版本对比
          </button>
        </div>
      </header>

      <main class="diff-a-board diff-a-board--knowledge" aria-label="知识库管理区">
        <aside class="diff-a-panel">
          <header class="diff-a-panelHeader">
            <div class="diff-a-h">
              <b>目录树</b>
              <span>facet · filter · list</span>
            </div>
            <span class="diff-a-tag">catalog</span>
          </header>

          <div class="diff-a-panelBody">
            <KnowledgeToolbar v-model:activeKind="activeKind" @create="handleCreate" @refresh="refreshCatalog" />

            <div class="field">
              <strong>目录筛选</strong>
              <div class="field-inline knowledge-filter-input">
                <input v-model="searchText" placeholder="按 ID / 名称 / 类型筛选" />
              </div>
            </div>

            <div class="facet">启用组件 {{ componentEnabled }}</div>
            <div class="facet">启用规则 {{ ruleEnabled }}</div>

            <KnowledgeListPanel
              :components="components"
              :rules="rules"
              :activeKind="activeKind"
              :selectedId="selectedId"
              :searchText="searchText"
              @select="handleSelect"
            />
          </div>
        </aside>

        <section ref="editorHost" class="diff-a-panel">
          <header class="diff-a-panelHeader">
            <div class="diff-a-h">
              <b>{{ activeKind === 'component' ? editorTitle : '规则编辑器' }}</b>
              <span>{{ activeKind === 'component' ? 'component' : 'rule' }}</span>
            </div>
            <span class="diff-a-tag">editor</span>
          </header>

          <div class="diff-a-panelBody">
            <p
              v-if="message"
              class="diff-a-msg"
              :class="message.type"
              role="status"
              aria-live="polite"
            >
              {{ message.text }}
            </p>

            <p v-if="loadingEditor" class="diff-a-msg info" role="status">加载中</p>

            <template v-else>
              <ComponentEditor
                v-if="activeKind === 'component'"
                :draft="componentDraft"
                @save="handleSaveComponent"
                @delete="handleDeleteActive"
              />
              <RuleEditor
                v-else
                :draft="ruleDraft"
                @save="handleSaveRule"
                @validate="handleValidateRule"
                @test="handleTestRule"
                @invalid="handleInvalidRuleInput"
                @delete="handleDeleteActive"
              />
            </template>
          </div>
        </section>

        <aside class="diff-a-panel">
          <header class="diff-a-panelHeader">
            <div class="diff-a-h">
              <b>预览与运行</b>
              <span>images · validate · test</span>
            </div>
            <span class="diff-a-tag">runner</span>
          </header>

          <div class="diff-a-panelBody">
            <div class="diff-a-note">
              <b>目录状态</b>：{{ loadingCatalog ? '目录加载中' : '目录就绪' }}
            </div>

            <div class="diff-a-note" style="display: grid; gap: 10px">
              <div class="diff-a-h">
                <b>{{ activeKind === 'component' ? '图片维护' : '图片上传' }}</b>
                <span>images</span>
              </div>

              <template v-if="activeKind === 'component'">
                <div class="image-actions">
                  <label class="upload-box">
                    <span>上传主图</span>
                    <input
                      type="file"
                      name="primaryImage"
                      accept="image/png,image/jpeg,image/webp"
                      @change="(e) => handleComponentImageUpload(e, 'primary')"
                    />
                  </label>
                  <label class="upload-box">
                    <span>新增变体图</span>
                    <input
                      type="file"
                      name="variantImage"
                      accept="image/png,image/jpeg,image/webp"
                      @change="(e) => handleComponentImageUpload(e, 'variant')"
                    />
                  </label>
                </div>
                <div class="image-preview-grid" v-if="componentDraft">
                  <template v-if="componentDraft.image_url">
                    <figure class="image-preview-card">
                      <div class="image-preview-canvas">
                        <img :src="componentDraft.image_url" :alt="componentDraft.label || componentDraft.id + ' 主图'" />
                      </div>
                      <figcaption>
                        <strong>主图</strong>
                        <span>{{ componentDraft.image_path || componentDraft.image_url }}</span>
                      </figcaption>
                    </figure>
                  </template>
                  <figure
                    v-for="(url, index) in (componentDraft.variant_image_urls || [])"
                    :key="index"
                    class="image-preview-card"
                  >
                    <div class="image-preview-canvas">
                      <img :src="url" :alt="componentDraft.label || componentDraft.id + ' 变体 ' + (index + 1)" />
                    </div>
                    <figcaption>
                      <strong>变体 {{ index + 1 }}</strong>
                      <span>{{ (componentDraft.variant_images || [])[index] || url }}</span>
                    </figcaption>
                  </figure>
                  <div
                    v-if="!componentDraft.image_url && !(componentDraft.variant_image_urls || []).length"
                    class="image-chip"
                  >
                    暂无图片
                  </div>
                </div>
                <div class="image-chip" v-else>选择单元件后维护图片</div>
              </template>

              <template v-else>
                <label class="upload-box compact">
                  <span>上传预览图</span>
                  <input type="file" name="ruleImage" accept="image/png,image/jpeg,image/webp" @change="handleRuleImageUpload" />
                </label>
                <div class="image-preview-grid" v-if="ruleDraft?.image_url">
                  <figure class="image-preview-card">
                    <div class="image-preview-canvas">
                      <img :src="ruleDraft.image_url" :alt="ruleDraft.name || ruleDraft.id" />
                    </div>
                  </figure>
                </div>
                <div v-else class="image-chip">暂无图片</div>
              </template>

              <div class="detail-row compact-row"><span>当前记录</span><b>{{ selectedId || '--' }}</b></div>
              <div class="detail-row compact-row"><span>对象类型</span><b>{{ activeKind === 'component' ? '单元件' : '组合元件' }}</b></div>
            </div>

            <div class="diff-a-note">
              <div class="diff-a-h">
                <b>试运行结果</b>
                <span>output</span>
              </div>
              <div style="margin-top: 8px; color: rgba(255, 255, 255, 0.72)">
                {{ message?.text || '执行校验或试运行后，这里回显结果摘要与错误提示。' }}
              </div>
            </div>
          </div>
        </aside>
      </main>
    </section>
  </div>
</template>

