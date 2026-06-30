import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import KnowledgeView from '../KnowledgeView.vue'

function createTestRouter() {
  return createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/', redirect: '/workbench' },
      { path: '/workbench', component: { template: '<div>WB</div>' } },
      { path: '/knowledge', component: KnowledgeView },
      { path: '/search', component: { template: '<div>Search</div>' } },
      { path: '/drawing-diff', component: { template: '<div>Diff</div>' } },
    ],
  })
}

describe('KnowledgeView', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method || 'GET'

      const json = (payload: unknown, status = 200) => Promise.resolve({
        ok: status >= 200 && status < 300,
        status,
        text: () => Promise.resolve(JSON.stringify(payload)),
        headers: { get: () => 'application/json' },
      })

      if (url.endsWith('/api/knowledge') && method === 'GET') {
        return json({
          count: 1,
          items: [{
            id: 'KM1',
            label: '接触器',
            image_path: '',
            image_url: '',
            variant_images: [],
            variant_image_urls: [],
            component_type: 'relay',
            model: 'CJX2',
            definition: '',
            standards: [],
            aliases: [],
            notes: '',
            source: '',
            enabled: true,
            created_at: '',
            updated_at: '',
          }],
        })
      }

      if (url.endsWith('/api/custom-rules') && method === 'GET') {
        return json({
          count: 1,
          items: [{
            id: 'RULE-1',
            name: '接触器组合',
            description: '',
            image_path: '',
            image_url: '',
            engine: 'declarative',
            enabled: true,
            scope: 'same_page',
            confidence: 0.95,
            aliases: [],
            notes: '',
            source: '',
            member_count: 1,
            members: [],
            created_at: '',
            updated_at: '',
          }],
        })
      }

      if (url.endsWith('/api/custom-rules/RULE-1') && method === 'GET') {
        return json({
          id: 'RULE-1',
          name: '接触器组合',
          description: '测试规则',
          image_path: '',
          image_url: '',
          engine: 'declarative',
          enabled: true,
          scope: 'same_page',
          confidence: 0.95,
          aliases: [],
          notes: '',
          source: '',
          member_count: 1,
          members: [{
            role: '主接触器',
            min_quantity: 1,
            component_ids: ['KM1'],
            code_patterns: [],
            label_keywords: [],
          }],
          created_at: '',
          updated_at: '',
        })
      }

      if (url.endsWith('/api/knowledge/KM1') && method === 'GET') {
        return json({
          id: 'KM1',
          label: '接触器',
          image_path: '',
          image_url: '',
          variant_images: [],
          variant_image_urls: [],
          component_type: 'relay',
          model: 'CJX2',
          definition: '',
          standards: [],
          aliases: [],
          notes: '',
          source: '',
          enabled: true,
          created_at: '',
          updated_at: '',
        })
      }

      if (url.endsWith('/api/custom-rules/validate') && method === 'POST') {
        return json({
          valid: true,
          summary: { member_count: 1, min_quantity_total: 1 },
          warnings: [],
        })
      }

      if (url.endsWith('/api/custom-rules/test') && method === 'POST') {
        return json({
          matches: [{ rule_id: 'RULE-1', name: '接触器组合' }],
        })
      }

      if (url.endsWith('/api/knowledge/KM1') && method === 'PUT') {
        return json({
          id: 'KM1',
          label: '接触器-已更新',
          image_path: '',
          image_url: '',
          variant_images: [],
          variant_image_urls: [],
          component_type: 'relay',
          model: 'CJX2',
          definition: '',
          standards: [],
          aliases: [],
          notes: '',
          source: '',
          enabled: true,
          created_at: '',
          updated_at: '',
        })
      }

      return json({ detail: 'not found' }, 404)
    }))
  })

  it('renders option c refined knowledge shell', async () => {
    const router = createTestRouter()
    await router.push('/knowledge')
    await router.isReady()

    const wrapper = mount(KnowledgeView, {
      global: { plugins: [router] },
    })

    expect(wrapper.find('.topbar.topbar--dark').exists()).toBe(true)
    expect(wrapper.find('.diff-a-shell').exists()).toBe(true)
    expect(wrapper.find('.diff-a-board').exists()).toBe(true)
    expect(wrapper.text()).toContain('单元件详情')
    expect(wrapper.text()).toContain('试运行结果')
    expect(wrapper.text()).toContain('目录树')
    expect(wrapper.text()).toContain('图片维护')
  })

  it('renders unit component and rule tabs', () => {
    const router = createTestRouter()
    router.push('/knowledge')

    const wrapper = mount(KnowledgeView, {
      global: { plugins: [router] },
    })

    expect(wrapper.text()).toContain('单元件')
    expect(wrapper.text()).toContain('组合元件')
  })

  it('uses option c refined screen hierarchy', () => {
    const router = createTestRouter()
    router.push('/knowledge')

    const wrapper = mount(KnowledgeView, {
      global: { plugins: [router] },
    })

    expect(wrapper.find('.topbar.topbar--dark').exists()).toBe(true)
    expect(wrapper.find('.diff-a-shell').exists()).toBe(true)
    expect(wrapper.find('.diff-a-topbar .diff-a-meta').exists()).toBe(true)
    expect(wrapper.find('.diff-a-board').exists()).toBe(true)
  })

  it('loads knowledge catalog on mount', async () => {
    const router = createTestRouter()
    await router.push('/knowledge')
    await router.isReady()

    mount(KnowledgeView, {
      global: { plugins: [router] },
    })

    await flushPromises()

    const calls = (globalThis.fetch as unknown as { mock: { calls: Array<[string, RequestInit | undefined]> } }).mock.calls
    expect(calls.some((call) => String(call[0]).endsWith('/api/knowledge'))).toBe(true)
    expect(calls.some((call) => String(call[0]).endsWith('/api/custom-rules'))).toBe(true)
  })

  it('loads rule detail and can validate and test the rule', async () => {
    const router = createTestRouter()
    await router.push('/knowledge')
    await router.isReady()

    const wrapper = mount(KnowledgeView, {
      global: { plugins: [router] },
    })

    await flushPromises()
    await wrapper.find('button.kind-tab:last-of-type').trigger('click')
    await flushPromises()
    await wrapper.find('button.list-item').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('接触器组合')
    expect(wrapper.find('[data-capability="compare-version"]').attributes('disabled')).toBeDefined()

    await wrapper.find('button[data-action="validate-rule"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('规则校验通过')
    await wrapper.find('button[data-action="test-rule"]').trigger('click')
    await flushPromises()

    const calls = (globalThis.fetch as unknown as { mock: { calls: Array<[string, RequestInit | undefined]> } }).mock.calls
    expect(calls.some((call) => String(call[0]).endsWith('/api/custom-rules/RULE-1'))).toBe(true)
    expect(calls.some((call) => String(call[0]).endsWith('/api/custom-rules/validate'))).toBe(true)
    expect(calls.some((call) => String(call[0]).endsWith('/api/custom-rules/test'))).toBe(true)
    expect(wrapper.text()).toContain('试运行命中 1 条结果')
  })

  it('loads component detail and saves updates through backend api', async () => {
    const router = createTestRouter()
    await router.push('/knowledge')
    await router.isReady()

    const wrapper = mount(KnowledgeView, {
      global: { plugins: [router] },
    })

    await flushPromises()
    await wrapper.find('button.list-item').trigger('click')
    await flushPromises()

    const labelInput = wrapper.find('input[name="label"]')
    await labelInput.setValue('接触器-已更新')
    await wrapper.find('form[data-form="component"]').trigger('submit')
    await flushPromises()

    const calls = (globalThis.fetch as unknown as { mock: { calls: Array<[string, RequestInit | undefined]> } }).mock.calls
    expect(calls.some((call) => String(call[0]).endsWith('/api/knowledge/KM1') && (call[1]?.method || 'GET') === 'PUT')).toBe(true)
    expect(wrapper.text()).toContain('单元件已保存')
  })
})

