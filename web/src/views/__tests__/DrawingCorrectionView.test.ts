import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import DrawingCorrectionView from '../DrawingCorrectionView.vue'

function createTestRouter() {
  return createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/', redirect: '/workbench' },
      { path: '/workbench', component: { template: '<div>Workbench</div>' } },
      { path: '/search', component: { template: '<div>Search</div>' } },
      { path: '/drawing-diff', component: { template: '<div>Diff</div>' } },
      { path: '/drawing-correction', component: DrawingCorrectionView },
      { path: '/knowledge', component: { template: '<div>Knowledge</div>' } },
      { path: '/results/:resultId', component: { template: '<div>Result</div>' } },
    ],
  })
}

describe('DrawingCorrectionView', () => {
  beforeEach(() => {
    vi.useRealTimers()
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/config')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () => Promise.resolve(JSON.stringify({
            model: 'qwen3.7-plus',
          })),
        })
      }
      if (url.endsWith('/api/results/correction-1')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () => Promise.resolve(JSON.stringify({
            result_id: 'correction-1',
            document: 'A17387_1706_项目原理图_06.pdf',
            status: 'complete',
            detected_components: [
              {
                label: '接触器',
                component_type: 'relay',
                code: 'KM1',
                page: 1,
                occurrence_count: 1,
                regions: [[100, 100, 180, 180]],
              },
              {
                label: '熔断器',
                component_type: 'fuse',
                code: 'FU1',
                page: 1,
                occurrence_count: 1,
                regions: [[220, 200, 280, 280]],
              },
            ],
            detected_combinations: [],
            title_block: {},
            control_signal_configuration: {},
            component_table: {
              rows: [
                { 元件代号: 'KM1', 元件名称: '交流接触器', 数量: 1 },
                { 元件代号: 'QF1', 元件名称: '断路器', 数量: 1 },
              ],
            },
            recognition_steps: {},
            warnings: [],
            meta: {},
            preview_pages: [
              {
                page: 1,
                width: 1000,
                height: 800,
                data_url: 'data:image/png;base64,page-1',
              },
            ],
            result_files: {},
          })),
        })
      }
      if (url.endsWith('/api/results/correction-1/steps')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () => Promise.resolve(JSON.stringify({
            result_id: 'correction-1',
            status: 'complete',
            steps: {
              recognition_log: [
                { time: '10:00:00', stage: 'vision_model', level: 'info', message: '准备调用视觉模型' },
              ],
            },
            files: {},
            missing: [],
          })),
        })
      }
      if (url.endsWith('/api/results/correction-1/manifest')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () => Promise.resolve(JSON.stringify({
            result_id: 'correction-1',
            created_at: '2026-06-26T10:00:00Z',
            updated_at: '2026-06-26T10:00:01Z',
            status: 'complete',
            document: 'A17387_1706_项目原理图_06.pdf',
          })),
        })
      }
      return Promise.resolve({
        ok: false,
        status: 404,
        text: () => Promise.resolve(JSON.stringify({ detail: `Unhandled ${url}` })),
      })
    }))
  })

  it('uses an adapted correction comparison layout for wide tables', async () => {
    const router = createTestRouter()
    await router.push('/drawing-correction')
    await router.isReady()

    const wrapper = mount(DrawingCorrectionView, {
      global: {
        plugins: [router],
        stubs: {
          DrawingPreview: { template: '<div class="drawing-preview-stub"></div>' },
          RecognitionLogPanel: { template: '<div class="recognition-log-stub"></div>' },
          UploadPanel: {
            emits: ['submitted'],
            template: '<button class="stub-upload" @click="$emit(\'submitted\', { task_id: \'task-1\', result_id: \'correction-1\', status: \'running\', result_url: \'\', steps_url: \'\' })">submit</button>',
          },
        },
      },
    })

    await wrapper.find('.stub-upload').trigger('click')
    await flushPromises()

    expect(wrapper.find('.drawing-correction-split').exists()).toBe(true)
    expect(wrapper.find('.drawing-correction-side').exists()).toBe(true)
    expect(wrapper.find('.drawing-correction-list').exists()).toBe(true)
    expect(wrapper.find('.component-identification-side').exists()).toBe(false)
    expect(wrapper.findAll('.label-compare-section')).toHaveLength(4)
    expect(wrapper.text()).toContain('名称不一致')
    expect(wrapper.text()).toContain('数量不一致')
    expect(wrapper.text()).toContain('BOM 存在但识别缺失')
  })
})

