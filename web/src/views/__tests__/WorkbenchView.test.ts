import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import WorkbenchView from '../WorkbenchView.vue'

function createTestRouter() {
  return createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/', redirect: '/workbench' },
      { path: '/workbench', component: WorkbenchView },
      { path: '/results/:resultId', component: { template: '<div>Result</div>' } },
      { path: '/knowledge', component: { template: '<div>Knowledge</div>' } },
      { path: '/search', component: { template: '<div>Search</div>' } },
      { path: '/drawing-diff', component: { template: '<div>Diff</div>' } },
      { path: '/drawing-correction', component: { template: '<div>Correction</div>' } },
    ],
  })
}

describe('WorkbenchView', () => {
  beforeEach(() => {
    vi.useRealTimers()
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/config')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () => Promise.resolve(JSON.stringify({
            model: 'gpt-4.1',
            api_key_configured: true,
            knowledge_path: 'data/index/components.json',
            component_count: 12,
            custom_rules_path: 'data/index/custom_rules.json',
            custom_rule_count: 2,
            reference_batch_size: 4,
            recognition_mode: 'hybrid',
            layout_routing_enabled: true,
            layout_router_mode: 'hybrid',
            search_enabled: true,
            search_mode: 'hybrid',
            search_auto_index: false,
            open_recognition_concurrency: 2,
            correction_batch_size: 8,
            correction_candidate_limit: 5,
          })),
        })
      }
      if (url.endsWith('/analyze')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () => Promise.resolve(JSON.stringify({
            task_id: 'demo-result',
            result_id: 'demo-result',
            status: 'running',
            result_url: '/results/demo-result',
            steps_url: '/api/results/demo-result/steps',
          })),
        })
      }

      if (url.endsWith('/api/results/demo-result')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () => Promise.resolve(JSON.stringify({
            result_id: 'demo-result',
            document: 'demo.pdf',
            status: 'complete',
            detected_components: [
              { id: 'KM1', label: '接触器', component_type: 'relay', page: 1 },
              { id: 'KM1', label: '接触器', component_type: 'relay', page: 2 },
              { id: 'FU1', label: '熔断器', component_type: 'fuse', page: 1 },
            ],
            detected_combinations: [
              {
                id: 'combo-1',
                rule_id: 'rule-custom-1',
                name: '自定义组合1',
                rule_layer: 'custom',
                page: 3,
                evidence: 'KM1 + FU1',
                members: [
                  { code: 'KM1', label: '接触器' },
                  { code: 'FU1', label: '熔断器' },
                ],
              },
            ],
            title_block: {},
            control_signal_configuration: {},
            component_table: {},
            recognition_steps: {},
            warnings: [],
            meta: {},
            preview_pages: [],
          })),
        })
      }

      if (url.endsWith('/api/results/demo-result/steps')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () => Promise.resolve(JSON.stringify({
            result_id: 'demo-result',
            status: 'complete',
            steps: {
              recognition_log: [
                {
                  time: '2026-06-25T17:07:41+08:00',
                  stage: 'vision_model',
                  level: 'info',
                  message: '已准备图纸整页图，准备调用视觉模型。',
                },
              ],
            },
            files: {},
            missing: [],
          })),
        })
      }

      if (url.endsWith('/api/results/demo-result/manifest')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () => Promise.resolve(JSON.stringify({
            result_id: 'demo-result',
            created_at: '2026-06-25T00:00:00+08:00',
            updated_at: '2026-06-25T00:10:00+08:00',
            status: 'complete',
            document: 'demo.pdf',
          })),
        })
      }

      return Promise.resolve({
        ok: false,
        status: 404,
        text: () => Promise.resolve(JSON.stringify({ detail: 'not found' })),
      })
    }))
  })

  it('renders option c refined workbench shell', async () => {
    const router = createTestRouter()
    await router.push('/workbench')
    await router.isReady()

    const wrapper = mount(WorkbenchView, {
      global: { plugins: [router] },
    })

    expect(wrapper.find('.topbar.topbar--dark').exists()).toBe(true)
    expect(wrapper.find('.diff-a-shell').exists()).toBe(true)
    expect(wrapper.find('.diff-a-topbar').exists()).toBe(true)
    expect(wrapper.find('.diff-a-board').exists()).toBe(true)
    expect(wrapper.text()).toContain('识别结果')
    expect(wrapper.text()).toContain('元件标识')
    expect(wrapper.text()).not.toContain('元件识别列表')
    expect(wrapper.text()).not.toContain('输出 元件列表')
    expect(wrapper.text()).not.toContain('DPI 220')
    expect(wrapper.text()).not.toContain('结果摘要')
    expect(wrapper.find('[data-capability="export-report"]').exists()).toBe(false)
    expect(wrapper.find('[data-capability="batch-review"]').exists()).toBe(false)
  })

  it('renders file input', () => {
    const router = createTestRouter()
    router.push('/workbench')

    const wrapper = mount(WorkbenchView, {
      global: { plugins: [router] },
    })

    const fileInput = wrapper.find('input[type="file"]')
    expect(fileInput.exists()).toBe(true)
  })

  it('renders navigation links', () => {
    const router = createTestRouter()
    router.push('/workbench')

    const wrapper = mount(WorkbenchView, {
      global: { plugins: [router] },
    })

    expect(wrapper.text()).toContain('知识库管理')
    expect(wrapper.text()).toContain('图纸检索')
  })

  it('uses option c refined screen hierarchy', () => {
    const router = createTestRouter()
    router.push('/workbench')

    const wrapper = mount(WorkbenchView, {
      global: { plugins: [router] },
    })

    expect(wrapper.find('.topbar.topbar--dark').exists()).toBe(true)
    expect(wrapper.find('.diff-a-shell').exists()).toBe(true)
    expect(wrapper.find('.diff-a-topbar .diff-a-meta').exists()).toBe(true)
    expect(wrapper.find('.diff-a-board').exists()).toBe(true)
  })

  it('submits analyze task and shows pipeline result context', async () => {
    const router = createTestRouter()
    await router.push('/workbench')
    await router.isReady()

    const wrapper = mount(WorkbenchView, {
      global: { plugins: [router] },
    })

    const file = new File(['demo'], 'demo.pdf', { type: 'application/pdf' })
    const fileInput = wrapper.find('input[type="file"]')
    Object.defineProperty(fileInput.element, 'files', {
      value: [file],
      configurable: true,
    })

    await fileInput.trigger('change')
    await wrapper.find('form.toolbar-upload').trigger('submit')
    await flushPromises()

    const calls = (globalThis.fetch as unknown as { mock: { calls: Array<[string]> } }).mock.calls
    expect(calls.some((call) => String(call[0]).endsWith('/analyze'))).toBe(true)
    expect(calls.some((call) => String(call[0]).endsWith('/api/results/demo-result'))).toBe(true)
    expect(calls.some((call) => String(call[0]).endsWith('/api/results/demo-result/manifest'))).toBe(true)
    expect(wrapper.text()).toContain('demo-result')
    expect(wrapper.text()).toContain('接触器')
    expect(wrapper.text()).toContain('元件代号')
    expect(wrapper.text()).toContain('类型')
    expect(wrapper.text()).toContain('页码')
    expect(wrapper.text()).toContain('KM1')
    expect(wrapper.text()).toContain('接触器')
    expect(wrapper.text()).not.toContain('结果摘要')
    expect(wrapper.text()).not.toContain('元件识别列表')
    expect(wrapper.text()).toContain('第 1 页')
  })

  it('shows vision model name in recognition log', async () => {
    const router = createTestRouter()
    await router.push('/workbench')
    await router.isReady()

    const wrapper = mount(WorkbenchView, {
      global: { plugins: [router] },
    })

    const file = new File(['demo'], 'demo.pdf', { type: 'application/pdf' })
    const fileInput = wrapper.find('input[type="file"]')
    Object.defineProperty(fileInput.element, 'files', {
      value: [file],
      configurable: true,
    })

    await fileInput.trigger('change')
    await wrapper.find('form.toolbar-upload').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('准备调用视觉模型')
    expect(wrapper.text()).toContain('gpt-4.1')
  })

  it('uses component identification tab layout in workbench', async () => {
    const router = createTestRouter()
    await router.push('/workbench')
    await router.isReady()

    const wrapper = mount(WorkbenchView, {
      global: { plugins: [router] },
    })

    const file = new File(['demo'], 'demo.pdf', { type: 'application/pdf' })
    const fileInput = wrapper.find('input[type="file"]')
    Object.defineProperty(fileInput.element, 'files', {
      value: [file],
      configurable: true,
    })

    await fileInput.trigger('change')
    await wrapper.find('form.toolbar-upload').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('元件标识')
    expect(wrapper.text()).toContain('图纸标签表')
    expect(wrapper.text()).toContain('控制/信号信息')
    expect(wrapper.text()).toContain('图签信息')
    expect(wrapper.text()).not.toContain('元件识别列表')
    expect(wrapper.text()).not.toContain('预览 (')
  })

  it('shows combination details in workbench combination tab', async () => {
    const router = createTestRouter()
    await router.push('/workbench')
    await router.isReady()

    const wrapper = mount(WorkbenchView, {
      global: { plugins: [router] },
    })

    const file = new File(['demo'], 'demo.pdf', { type: 'application/pdf' })
    const fileInput = wrapper.find('input[type="file"]')
    Object.defineProperty(fileInput.element, 'files', {
      value: [file],
      configurable: true,
    })

    await fileInput.trigger('change')
    await wrapper.find('form.toolbar-upload').trigger('submit')
    await flushPromises()

    const comboTab = wrapper.findAll('.tab-button').find((button) => button.text().includes('组合'))
    expect(comboTab).toBeTruthy()
    await comboTab!.trigger('click')

    expect(wrapper.find('.component-identification-split').exists()).toBe(true)
    expect(wrapper.find('.component-identification-preview').exists()).toBe(true)
    expect(wrapper.text()).toContain('组合规则信息')
    expect(wrapper.text()).toContain('自定义组合1')
    expect(wrapper.text()).toContain('第 3 页')
    expect(wrapper.text()).toContain('KM1')
    expect(wrapper.text()).toContain('FU1')
    expect(wrapper.text()).toContain('KM1 + FU1')
  })

  it('backfills workbench detail tabs from completed step payloads while result is still running', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/config')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () => Promise.resolve(JSON.stringify({
            model: 'gpt-4.1',
            api_key_configured: true,
          })),
        })
      }
      if (url.endsWith('/analyze')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () => Promise.resolve(JSON.stringify({
            task_id: 'demo-result',
            result_id: 'demo-result',
            status: 'running',
            result_url: '/results/demo-result',
            steps_url: '/api/results/demo-result/steps',
          })),
        })
      }
      if (url.endsWith('/api/results/demo-result')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () => Promise.resolve(JSON.stringify({
            result_id: 'demo-result',
            document: 'demo.pdf',
            status: 'running',
            detected_components: [],
            detected_combinations: [],
            title_block: {},
            control_signal_configuration: {},
            component_table: {},
            recognition_steps: {},
            warnings: [],
            meta: {},
            preview_pages: [],
          })),
        })
      }
      if (url.endsWith('/api/results/demo-result/steps')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () => Promise.resolve(JSON.stringify({
            result_id: 'demo-result',
            status: 'running',
            steps: {
              recognition_log: [
                {
                  time: '2026-06-25T17:07:41+08:00',
                  stage: 'component_table',
                  level: 'info',
                  message: '图纸标签表提取完成。',
                },
              ],
              component_table: {
                columns: ['code', 'name'],
                rows: [
                  { code: 'KM1', name: 'contactor' },
                ],
              },
              title_block: {
                fields: {
                  drawing_name: 'Starter Diagram',
                },
              },
              control_signal_configuration: {
                signal_inputs: [
                  { name: 'START', terminal: 'X1' },
                ],
              },
            },
            files: {},
            missing: [],
          })),
        })
      }
      return Promise.resolve({
        ok: false,
        status: 404,
        text: () => Promise.resolve(JSON.stringify({ detail: 'not found' })),
      })
    }))

    const router = createTestRouter()
    await router.push('/workbench')
    await router.isReady()

    const wrapper = mount(WorkbenchView, {
      global: { plugins: [router] },
    })

    const file = new File(['demo'], 'demo.pdf', { type: 'application/pdf' })
    const fileInput = wrapper.find('input[type="file"]')
    Object.defineProperty(fileInput.element, 'files', {
      value: [file],
      configurable: true,
    })

    await fileInput.trigger('change')
    await wrapper.find('form.toolbar-upload').trigger('submit')
    await flushPromises()
    await flushPromises()

    const tabs = wrapper.findAll('.tab-button')
    await tabs[2].trigger('click')
    expect(wrapper.text()).toContain('KM1')
    expect(wrapper.text()).toContain('contactor')

    await tabs[4].trigger('click')
    expect(wrapper.text()).toContain('drawing_name')
    expect(wrapper.text()).toContain('Starter Diagram')

    await tabs[3].trigger('click')
    expect(wrapper.text()).toContain('START')
    expect(wrapper.text()).toContain('X1')
  })
})
