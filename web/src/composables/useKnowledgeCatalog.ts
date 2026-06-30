import { ref } from 'vue'
import {
  fetchKnowledge,
  fetchCustomRules,
  getComponent,
  getRule,
  createComponent,
  updateComponent,
  deleteComponent,
  createRule,
  updateRule,
  deleteRule,
} from '../api/knowledge'
import type { ComponentItem, RuleItem } from '../types/knowledge'

export type EditorKind = 'component' | 'rule'

export function useKnowledgeCatalog() {
  const components = ref<ComponentItem[]>([])
  const rules = ref<RuleItem[]>([])
  const loading = ref(false)
  const activeKind = ref<EditorKind>('component')
  const selectedId = ref('')
  const draft = ref<ComponentItem | RuleItem | null>(null)

  async function load() {
    loading.value = true
    try {
      const [componentPayload, rulePayload] = await Promise.all([
        fetchKnowledge(),
        fetchCustomRules(),
      ])
      components.value = componentPayload.items ?? []
      rules.value = rulePayload.items ?? []
    } finally {
      loading.value = false
    }
  }

  async function selectItem(kind: EditorKind, id: string) {
    activeKind.value = kind
    selectedId.value = id
    try {
      draft.value = kind === 'component'
        ? await getComponent(id)
        : await getRule(id)
    } catch {
      draft.value = null
    }
  }

  function createNew(kind: EditorKind) {
    activeKind.value = kind
    selectedId.value = ''
    if (kind === 'component') {
      draft.value = {
        id: '', label: '', image_path: '', image_url: '', variant_images: [], variant_image_urls: [],
        component_type: '', model: '', definition: '', standards: [], aliases: [], notes: '',
        source: '', enabled: true, created_at: '', updated_at: '',
      } as ComponentItem
    } else {
      draft.value = {
        id: '', name: '', description: '', image_path: '', image_url: '',
        engine: 'declarative', enabled: true, scope: 'same_page', confidence: 0.95,
        aliases: [], notes: '', source: '', member_count: 0, members: [],
        created_at: '', updated_at: '',
      } as RuleItem
    }
  }

  async function save() {
    if (!draft.value) return
    const kind = activeKind.value
    const id = (draft.value as { id: string }).id
    if (!id) throw new Error('ID 不能为空')
    const payload = { ...draft.value }
    if (selectedId.value) {
      const updated = kind === 'component'
        ? await updateComponent(id, payload)
        : await updateRule(id, payload)
      draft.value = updated
      await load()
    } else {
      const created = kind === 'component'
        ? await createComponent(payload)
        : await createRule(payload)
      draft.value = created
      selectedId.value = created.id
      await load()
    }
  }

  async function remove() {
    if (!draft.value) return
    const id = (draft.value as { id: string }).id
    if (!id) return
    if (activeKind.value === 'component') {
      await deleteComponent(id)
    } else {
      await deleteRule(id)
    }
    draft.value = null
    selectedId.value = ''
    await load()
  }

  const filteredComponents = () => components.value
  const filteredRules = () => rules.value

  return {
    components, rules, loading, activeKind, selectedId, draft,
    load, selectItem, createNew, save, remove,
    filteredComponents, filteredRules,
  }
}
