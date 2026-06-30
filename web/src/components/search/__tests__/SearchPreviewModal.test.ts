import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SearchPreviewModal from '../SearchPreviewModal.vue'
import type { SearchResultItem } from '../../../types/search'

const item: SearchResultItem = {
  drawing_id: 'drawing-1',
  result_id: 'result-1',
  filename: 'demo.pdf',
  drawing_number: 'A17387_1706',
  drawing_title: '风机控制图',
  revision: 'B',
  project_name: 'Project',
  system_name: 'System',
  score: 0.88,
  matched_pages: [1, 3],
  matched_components: [],
  matched_combinations: [],
  matched_chunk_types: [],
  snippet: 'snippet',
  match_sources: [],
  preview_url: '/api/results/result-1/preview-file#page-1',
  source_hash: '',
  collapsed_versions: 0,
  history_versions: [],
  debug: {},
}

describe('SearchPreviewModal', () => {
  it('renders matched page navigation and emits close', async () => {
    const wrapper = mount(SearchPreviewModal, {
      props: { open: true, item },
      attachTo: document.body,
    })

    expect(document.body.textContent).toContain('打开图纸预览')
    expect(document.body.textContent).toContain('第 1 页')
    expect(document.body.textContent).toContain('第 3 页')

    ;(document.body.querySelector('[data-action="close-preview"]') as HTMLButtonElement)?.click()
    expect(wrapper.emitted('close')).toHaveLength(1)
    wrapper.unmount()
  })

  it('switches preview iframe by matched page while preserving preview_url base', async () => {
    const wrapper = mount(SearchPreviewModal, {
      props: {
        open: true,
        item: {
          ...item,
          matched_pages: [2, 5],
          preview_url: '/api/previews/result-1?mode=embed#page-9',
        },
      },
      attachTo: document.body,
    })

    expect(document.body.querySelector('iframe')?.getAttribute('src')).toBe(
      '/api/previews/result-1?mode=embed#page-2',
    )

    ;(Array.from(document.body.querySelectorAll('.search-preview-page')).find((node) =>
      node.textContent?.includes('第 5 页'),
    ) as HTMLButtonElement | undefined)?.click()

    await wrapper.vm.$nextTick()

    expect(document.body.querySelector('iframe')?.getAttribute('src')).toBe(
      '/api/previews/result-1?mode=embed#page-5',
    )
    wrapper.unmount()
  })

  it('falls back to preview root when matched pages are missing', () => {
    const wrapper = mount(SearchPreviewModal, {
      props: {
        open: true,
        item: {
          ...item,
          matched_pages: [],
          preview_url: '/api/results/result-1/preview-file#page-9',
        },
      },
      attachTo: document.body,
    })

    expect(document.body.textContent).toContain('未定位具体页码，默认展示首页')
    expect(document.body.querySelector('iframe')?.getAttribute('src')).toBe('/api/results/result-1/preview-file')
    wrapper.unmount()
  })

  it('scales internal page previews as images', () => {
    const wrapper = mount(SearchPreviewModal, {
      props: {
        open: true,
        item: {
          ...item,
          matched_pages: [2],
          preview_url: '/results/result-1#page-9',
        },
      },
      attachTo: document.body,
    })

    const image = document.body.querySelector('.search-preview-image') as HTMLImageElement | null
    expect(image?.getAttribute('src')).toBe('/api/results/result-1/preview-page/2')
    expect(document.body.querySelector('.search-preview-frame')?.classList.contains('search-preview-frame--image')).toBe(
      true,
    )
    expect(document.body.querySelector('iframe')).toBeNull()
    wrapper.unmount()
  })

  it('uses scaled page images when preview_url is missing', () => {
    const { preview_url: _previewUrl, ...itemWithoutPreview } = item
    const wrapper = mount(SearchPreviewModal, {
      props: {
        open: true,
        item: {
          ...itemWithoutPreview,
          matched_pages: [4],
        },
      },
      attachTo: document.body,
    })

    expect(document.body.querySelector('.search-preview-image')?.getAttribute('src')).toBe(
      '/api/results/result-1/preview-page/4',
    )
    expect(document.body.querySelector('.search-preview-image')?.getAttribute('src')).not.toBe('/results/result-1#page-4')
    wrapper.unmount()
  })
})
