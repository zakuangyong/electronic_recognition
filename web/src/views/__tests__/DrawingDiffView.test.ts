import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import DrawingDiffView from '../DrawingDiffView.vue'

function createTestRouter() {
  return createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/', redirect: '/workbench' },
      { path: '/workbench', component: { template: '<div>Workbench</div>' } },
      { path: '/knowledge', component: { template: '<div>Knowledge</div>' } },
      { path: '/search', component: { template: '<div>Search</div>' } },
      { path: '/drawing-diff', component: DrawingDiffView },
      { path: '/drawing-correction', component: { template: '<div>Correction</div>' } },
    ],
  })
}

describe('DrawingDiffView', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const body = init?.body as FormData | undefined
      const submittedFileType = body?.get('file_type')?.toString() ?? 'catdrawing'
      const oldName = body?.get('old_file') instanceof File
        ? (body.get('old_file') as File).name
        : 'old.CATDrawing'
      const newName = body?.get('new_file') instanceof File
        ? (body.get('new_file') as File).name
        : 'new.CATDrawing'
      if (url.endsWith('/api/diff/compare')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () => Promise.resolve(JSON.stringify({
            success: true,
            message: 'compare completed',
            stage: 'completed',
            job_id: 'job-1',
            error_code: '',
            data: {
              summary: {
                old_filename: oldName,
                new_filename: newName,
                page_count: 1,
                total_diff_count: 2,
                status: 'completed',
                duration_ms: null,
              },
              annotated_images: [
                { page: 1, image_url: '/api/diff/files/job-1/work/diff/page_001_annotated.png' },
              ],
              diff_items: [
                {
                  id: 'region_001',
                  page: 1,
                  bbox: [100, 120, 180, 200],
                  crop_image_url: '/api/diff/files/job-1/work/diff/crops/region.png',
                  old_text: '',
                  new_text: 'KM1',
                  changed_type: 'visual_change',
                },
                {
                  id: 'region_002',
                  page: 1,
                  bbox: [300, 220, 420, 340],
                  crop_image_url: '/api/diff/files/job-1/work/diff/crops/region2.png',
                  old_text: 'K1',
                  new_text: 'K2',
                  changed_type: 'text_changed',
                },
              ],
              downloads: {
                summary_json_url: '/api/diff/files/job-1/output/summary.json',
                excel_report_url: '/api/diff/files/job-1/output/diff_report.xlsx',
              },
              artifacts: {},
              file_type: submittedFileType,
            },
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

  it('renders the drawing diff workbench shell', async () => {
    const router = createTestRouter()
    await router.push('/drawing-diff')
    await router.isReady()

    const wrapper = mount(DrawingDiffView, {
      global: { plugins: [router] },
    })

    expect(wrapper.find('.topbar.topbar--dark').exists()).toBe(true)
    expect(wrapper.text()).toContain('图纸比对')
    expect(wrapper.text()).toContain('比对输入')
    expect(wrapper.text()).toContain('差异清单')
    expect(wrapper.findAll('input[type="file"]')).toHaveLength(2)
  })

  it('submits compare request and renders diff results', async () => {
    const router = createTestRouter()
    await router.push('/drawing-diff')
    await router.isReady()

    const wrapper = mount(DrawingDiffView, {
      global: { plugins: [router] },
    })

    const inputs = wrapper.findAll('input[type="file"]')
    Object.defineProperty(inputs[0].element, 'files', {
      value: [new File(['old'], 'old.CATDrawing')],
      configurable: true,
    })
    Object.defineProperty(inputs[1].element, 'files', {
      value: [new File(['new'], 'new.CATDrawing')],
      configurable: true,
    })

    await inputs[0].trigger('change')
    await inputs[1].trigger('change')
    await wrapper.find('.diff-a-start').trigger('click')
    await flushPromises()

    const calls = (globalThis.fetch as unknown as any).mock.calls
    expect(calls.some((call: any[]) => String(call[0]).endsWith('/api/diff/compare'))).toBe(true)
    expect(wrapper.text()).toContain('比对完成：job-1')
    expect(wrapper.text()).toContain('old.CATDrawing')
    expect(wrapper.text()).toContain('new.CATDrawing')
    expect(wrapper.text()).toContain('region_001')
    expect(wrapper.text()).toContain('KM1')
    expect(wrapper.text()).toContain('region_002')
    expect(wrapper.text()).toContain('K2')
  })

  it('focuses again when selecting another region after overview reset', async () => {
    const router = createTestRouter()
    await router.push('/drawing-diff')
    await router.isReady()

    const wrapper = mount(DrawingDiffView, {
      global: { plugins: [router] },
    })

    const inputs = wrapper.findAll('input[type="file"]')
    Object.defineProperty(inputs[0].element, 'files', {
      value: [new File(['old'], 'old.CATDrawing')],
      configurable: true,
    })
    Object.defineProperty(inputs[1].element, 'files', {
      value: [new File(['new'], 'new.CATDrawing')],
      configurable: true,
    })
    await inputs[0].trigger('change')
    await inputs[1].trigger('change')
    await wrapper.find('.diff-a-start').trigger('click')
    await flushPromises()

    const viewer = wrapper.get('[data-testid="diff-viewer"]')
    const reset = viewer.get('button')
    await reset.trigger('click')

    const first = wrapper.get('[data-testid="diff-item-region_001"]')
    const second = wrapper.get('[data-testid="diff-item-region_002"]')

    await first.trigger('click')
    await flushPromises()
    const world1 = viewer.attributes('data-world')
    expect(viewer.get('[data-testid="diff-zoom"]').text()).toBe('60%')

    await second.trigger('click')
    await flushPromises()
    const world2 = viewer.attributes('data-world')
    expect(viewer.get('[data-testid="diff-active-id"]').text()).toBe('region_002')
    expect(viewer.get('[data-testid="diff-zoom"]').text()).toBe('60%')
    expect(world2).not.toBe(world1)
  })

  it('accepts PDF drawing pairs and submits the pdf file type', async () => {
    const router = createTestRouter()
    await router.push('/drawing-diff')
    await router.isReady()

    const wrapper = mount(DrawingDiffView, {
      global: { plugins: [router] },
    })

    const inputs = wrapper.findAll('input[type="file"]')
    Object.defineProperty(inputs[0].element, 'files', {
      value: [new File(['old'], 'old.pdf', { type: 'application/pdf' })],
      configurable: true,
    })
    Object.defineProperty(inputs[1].element, 'files', {
      value: [new File(['new'], 'new.pdf', { type: 'application/pdf' })],
      configurable: true,
    })

    await inputs[0].trigger('change')
    await inputs[1].trigger('change')
    await wrapper.find('.diff-a-start').trigger('click')
    await flushPromises()

    const calls = (globalThis.fetch as unknown as any).mock.calls
    const compareCall = calls.find((call: any[]) => String(call[0]).endsWith('/api/diff/compare'))
    expect(compareCall).toBeTruthy()
    expect((compareCall[1].body as FormData).get('file_type')).toBe('pdf')
    expect(wrapper.text()).toContain('old.pdf')
    expect(wrapper.text()).toContain('new.pdf')
  })
})
