import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import ResultView from '../ResultView.vue'

function createTestRouter(resultId = 'test-result') {
  return createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/', redirect: '/workbench' },
      { path: '/workbench', component: { template: '<div>WB</div>' } },
      { path: '/results/:resultId', component: ResultView },
      { path: '/knowledge', component: { template: '<div>Knowledge</div>' } },
      { path: '/search', component: { template: '<div>Search</div>' } },
      { path: '/drawing-diff', component: { template: '<div>Diff</div>' } },
    ],
  })
}

describe('ResultView', () => {
  beforeEach(() => {
    vi.useRealTimers()
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/results/test-result')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () => Promise.resolve(JSON.stringify({
            result_id: 'test-result',
            document: 'test.pdf',
            status: 'complete',
            detected_components: [],
            detected_combinations: [],
            title_block: {},
            control_signal_configuration: {},
            component_table: {},
            recognition_steps: {},
            warnings: ['存在 1 条提示'],
            meta: { recognition_strategy: 'vision_first' },
            preview_pages: [],
            result_files: {},
          })),
        })
      }
      if (url.endsWith('/api/results/test-result/steps')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () => Promise.resolve(JSON.stringify({
            result_id: 'test-result',
            status: 'complete',
            steps: { document: { filename: 'test.pdf' }, detected_components: [] },
            files: { document: 'steps/00-document.json' },
            missing: [],
          })),
        })
      }
      if (url.endsWith('/api/results/test-result/manifest')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () => Promise.resolve(JSON.stringify({
            result_id: 'test-result',
            created_at: '2026-06-25T00:00:00+08:00',
            updated_at: '2026-06-25T00:10:00+08:00',
            status: 'complete',
            document: 'test.pdf',
            index_status: 'complete',
          })),
        })
      }
      if (url.endsWith('/api/results/test-result/error')) {
        return Promise.resolve({
          ok: false,
          status: 404,
          text: () => Promise.resolve(JSON.stringify({ detail: 'not found' })),
        })
      }
      return Promise.resolve({
        ok: false,
        status: 404,
        text: () => Promise.resolve(JSON.stringify({ detail: 'not found' })),
      })
    }))
  })

  it('renders result summary and navigation for existing result id', async () => {
    const router = createTestRouter()
    await router.push('/results/test-result')
    await router.isReady()

    const wrapper = mount(ResultView, {
      global: {
        plugins: [router],
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('识别结果')
    expect(wrapper.text()).toContain('识别工作台')
    expect(wrapper.text()).toContain('知识库管理')
    expect(wrapper.text()).toContain('test.pdf')
    expect(wrapper.text()).toContain('test-result')
    expect(wrapper.text()).toContain('存在 1 条提示')
    expect(wrapper.text()).toContain('索引状态')
  })

  it('shows loading state initially', () => {
    const router = createTestRouter()
    router.push('/results/test-result')

    const wrapper = mount(ResultView, {
      global: { plugins: [router] },
    })

    expect(wrapper.text()).toContain('加载中')
  })

  it('polls until result is complete', async () => {
    vi.useFakeTimers()
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        text: () => Promise.resolve(JSON.stringify({
          result_id: 'test-result',
          document: 'test.pdf',
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
          result_files: {},
        })),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        text: () => Promise.resolve(JSON.stringify({
          result_id: 'test-result',
          document: 'test.pdf',
          status: 'complete',
          detected_components: [{ id: 'C-1', label: '接触器', component_type: 'relay', page: 1 }],
          detected_combinations: [],
          title_block: {},
          control_signal_configuration: {},
          component_table: {},
          recognition_steps: {},
          warnings: [],
          meta: {},
          preview_pages: [],
          result_files: {},
        })),
      }))

    const router = createTestRouter()
    await router.push('/results/test-result')
    await router.isReady()

    const wrapper = mount(ResultView, {
      global: { plugins: [router] },
    })

    await flushPromises()
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()

    const calls = (globalThis.fetch as unknown as { mock: { calls: Array<[string]> } }).mock.calls
    expect(calls.filter((call) => String(call[0]).endsWith('/api/results/test-result')).length).toBeGreaterThanOrEqual(2)
    expect(wrapper.text()).toContain('已完成')
    expect(wrapper.text()).toContain('接触器')
  })

  it('loads result steps and manifest details', async () => {
    const router = createTestRouter()
    await router.push('/results/test-result')
    await router.isReady()

    const wrapper = mount(ResultView, {
      global: { plugins: [router] },
    })

    await flushPromises()

    const calls = (globalThis.fetch as unknown as { mock: { calls: Array<[string]> } }).mock.calls
    expect(calls.some((call) => String(call[0]).endsWith('/api/results/test-result/steps'))).toBe(true)
    expect(calls.some((call) => String(call[0]).endsWith('/api/results/test-result/manifest'))).toBe(true)
    expect(wrapper.text()).toContain('Pipeline 步骤')
    expect(wrapper.text()).toContain('updated_at')
  })

  it('uses a compact summary layout to prioritize result content', async () => {
    const router = createTestRouter()
    await router.push('/results/test-result')
    await router.isReady()

    const wrapper = mount(ResultView, {
      global: { plugins: [router] },
    })

    await flushPromises()

    expect(wrapper.find('.summary-grid.summary-grid--compact').exists()).toBe(true)
  })

  it('paginates items inside each result tab', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/results/test-result')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () => Promise.resolve(JSON.stringify({
            result_id: 'test-result',
            document: 'test.pdf',
            status: 'complete',
            detected_components: Array.from({ length: 13 }, (_, index) => ({
              id: `C-${index + 1}`,
              label: `元件-${index + 1}`,
              component_type: 'relay',
              page: 1,
            })),
            detected_combinations: Array.from({ length: 9 }, (_, index) => ({
              id: `R-${index + 1}`,
              rule_id: `RULE-${index + 1}`,
              name: `组合-${index + 1}`,
              rule_layer: 'custom',
              members: [],
              page: 1,
            })),
            title_block: {},
            control_signal_configuration: {},
            component_table: {},
            recognition_steps: {},
            warnings: [],
            meta: {},
            preview_pages: Array.from({ length: 5 }, (_, index) => ({
              page: index + 1,
              width: 1000,
              height: 800,
              data_url: `data:image/png;base64,page-${index + 1}`,
            })),
            result_files: {},
          })),
        })
      }
      if (url.endsWith('/api/results/test-result/steps')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () => Promise.resolve(JSON.stringify({
            result_id: 'test-result',
            status: 'complete',
            steps: {},
            files: {},
            missing: [],
          })),
        })
      }
      if (url.endsWith('/api/results/test-result/manifest')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () => Promise.resolve(JSON.stringify({
            result_id: 'test-result',
            created_at: '2026-06-25T00:00:00+08:00',
            updated_at: '2026-06-25T00:10:00+08:00',
            status: 'complete',
            document: 'test.pdf',
            index_status: 'complete',
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
    await router.push('/results/test-result')
    await router.isReady()

    const wrapper = mount(ResultView, {
      global: { plugins: [router] },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('元件-1')
    expect(wrapper.text()).not.toContain('元件-13')
    await wrapper.find('button.pagination-button:last-child').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('元件-13')

    await wrapper.find('button.tab-button:nth-child(2)').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('组合-1')
    expect(wrapper.text()).not.toContain('组合-9')
    await wrapper.find('button.pagination-button:last-child').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('组合-9')

    await wrapper.find('button.tab-button:nth-child(3)').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.drawing-preview-canvas img').length).toBe(1)
    expect(wrapper.text()).toContain('第 1 页')
    expect(wrapper.text()).toContain('1/5')
    await wrapper.find('.drawing-preview-pager .mini-button:last-child').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('第 2 页')
    expect(wrapper.text()).toContain('2/5')
  })

  it('keeps the latest route result when earlier requests resolve late', async () => {
    type DeferredResponse = {
      promise: Promise<{
        ok: boolean
        status: number
        text: () => Promise<string>
      }>
      resolve: (value: {
        ok: boolean
        status: number
        text: () => Promise<string>
      }) => void
    }

    function deferred(): DeferredResponse {
      let resolve!: DeferredResponse['resolve']
      const promise = new Promise<{
        ok: boolean
        status: number
        text: () => Promise<string>
      }>((innerResolve) => {
        resolve = innerResolve
      })
      return { promise, resolve }
    }

    const firstResult = deferred()
    const firstSteps = deferred()
    const firstManifest = deferred()

    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/results/first-result')) return firstResult.promise
      if (url.endsWith('/api/results/first-result/steps')) return firstSteps.promise
      if (url.endsWith('/api/results/first-result/manifest')) return firstManifest.promise
      if (url.endsWith('/api/results/second-result')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () => Promise.resolve(JSON.stringify({
            result_id: 'second-result',
            document: 'second.pdf',
            status: 'complete',
            detected_components: [],
            detected_combinations: [],
            title_block: {},
            control_signal_configuration: {},
            component_table: {},
            recognition_steps: {},
            warnings: [],
            meta: {},
            preview_pages: [],
            result_files: {},
          })),
        })
      }
      if (url.endsWith('/api/results/second-result/steps')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () => Promise.resolve(JSON.stringify({
            result_id: 'second-result',
            status: 'complete',
            steps: {},
            files: {},
            missing: [],
          })),
        })
      }
      if (url.endsWith('/api/results/second-result/manifest')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () => Promise.resolve(JSON.stringify({
            result_id: 'second-result',
            created_at: '2026-06-25T00:00:00+08:00',
            updated_at: '2026-06-25T00:10:00+08:00',
            status: 'complete',
            document: 'second.pdf',
            index_status: 'complete',
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
    await router.push('/results/first-result')
    await router.isReady()

    const wrapper = mount(ResultView, {
      global: { plugins: [router] },
    })

    await router.push('/results/second-result')
    await flushPromises()

    firstResult.resolve({
      ok: true,
      status: 200,
      text: () => Promise.resolve(JSON.stringify({
        result_id: 'first-result',
        document: 'first.pdf',
        status: 'complete',
        detected_components: [],
        detected_combinations: [],
        title_block: {},
        control_signal_configuration: {},
        component_table: {},
        recognition_steps: {},
        warnings: [],
        meta: {},
        preview_pages: [],
        result_files: {},
      })),
    })
    firstSteps.resolve({
      ok: true,
      status: 200,
      text: () => Promise.resolve(JSON.stringify({
        result_id: 'first-result',
        status: 'complete',
        steps: {},
        files: {},
        missing: [],
      })),
    })
    firstManifest.resolve({
      ok: true,
      status: 200,
      text: () => Promise.resolve(JSON.stringify({
        result_id: 'first-result',
        created_at: '2026-06-25T00:00:00+08:00',
        updated_at: '2026-06-25T00:05:00+08:00',
        status: 'complete',
        document: 'first.pdf',
        index_status: 'complete',
      })),
    })

    await flushPromises()

    expect(wrapper.text()).toContain('second.pdf')
    expect(wrapper.text()).not.toContain('first.pdf')
  })
})

