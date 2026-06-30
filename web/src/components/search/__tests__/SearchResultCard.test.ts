import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SearchResultCard from '../SearchResultCard.vue'

const item = {
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
  matched_components: ['KM1'],
  matched_combinations: ['电动机启动与保护'],
  matched_chunk_types: ['drawing'],
  snippet: '第 3 页出现热继保护相关描述',
  match_sources: ['bm25'],
  preview_url: '/results/result-1#page-1',
  source_hash: '',
  collapsed_versions: 0,
  history_versions: [],
  debug: {},
}

describe('SearchResultCard', () => {
  it('renders search-style hierarchy and emits open-preview', async () => {
    const wrapper = mount(SearchResultCard, {
      props: { item, index: 0 },
      global: {
        stubs: {
          RouterLink: {
            props: ['to'],
            template: '<a :href="to"><slot /></a>',
          },
        },
      },
    })

    expect(wrapper.text()).toContain('1')
    expect(wrapper.text()).not.toContain('相关度')
    expect(wrapper.text()).toContain('命中理由')
    expect(wrapper.text()).toContain('打开图纸')
    expect(wrapper.text()).not.toContain('查看结果')

    await wrapper.find('[data-action="open-preview"]').trigger('click')
    expect(wrapper.emitted('open-preview')).toHaveLength(1)
  })

  it('disables placeholder secondary actions and completes hit reason mapping', () => {
    const wrapper = mount(SearchResultCard, {
      props: {
        item: {
          ...item,
          matched_components: [],
          matched_combinations: [],
          matched_chunk_types: ['drawing'],
          match_sources: ['bm25', 'vector'],
        },
        index: 1,
      },
      global: {
        stubs: {
          RouterLink: {
            props: ['to'],
            template: '<a :href="to"><slot /></a>',
          },
        },
      },
    })

    const secondaryButtons = wrapper.findAll('.search-result-actions .result-action:not([data-action="open-preview"])')

    expect(wrapper.text()).toContain('关键词命中')
    expect(wrapper.text()).toContain('包含语义命中')
    expect(wrapper.text()).toContain('命中图纸页')
    expect(secondaryButtons).toHaveLength(2)
    expect(secondaryButtons[0].attributes('disabled')).toBeDefined()
    expect(secondaryButtons[1].attributes('disabled')).toBeDefined()
  })

  it('caps evidence tags to five and sorts them by value', () => {
    const wrapper = mount(SearchResultCard, {
      props: {
        item: {
          ...item,
          matched_pages: [1, 2, 3],
          matched_components: ['KM1', 'QF2', 'KA3'],
          matched_combinations: ['电动机启动与保护', '二级组合'],
          matched_chunk_types: ['drawing', 'component_table'],
          match_sources: ['bm25', 'vector'],
        },
        index: 0,
      },
    })

    const tags = wrapper.findAll('.search-tag').map((node) => node.text())

    expect(tags).toEqual(['KM1', 'QF2', '电动机启动与保护', '关键词命中', '包含语义命中'])
  })
})
