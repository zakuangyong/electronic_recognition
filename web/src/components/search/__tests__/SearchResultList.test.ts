import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SearchResultList from '../SearchResultList.vue'

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
  matched_combinations: [],
  matched_chunk_types: ['drawing'],
  snippet: 'snippet',
  match_sources: ['bm25'],
  preview_url: '/results/result-1#page-1',
  source_hash: '',
  collapsed_versions: 0,
  history_versions: [],
  debug: {},
}

describe('SearchResultList', () => {
  it('re-emits open-preview with the clicked result item', async () => {
    const wrapper = mount(SearchResultList, {
      props: {
        items: [item],
        total: 1,
        query: 'fan',
        retrievalMode: 'hybrid',
        loading: false,
      },
      global: {
        stubs: {
          SearchResultCard: {
            props: ['item', 'index'],
            emits: ['open-preview'],
            template: `
              <button
                type="button"
                data-action="open-preview"
                @click="$emit('open-preview')"
              >
                {{ item.drawing_title }}
              </button>
            `,
          },
        },
      },
    })

    await wrapper.find('[data-action="open-preview"]').trigger('click')

    expect(wrapper.emitted('open-preview')).toEqual([[item]])
  })

  it('passes the correct item through when multiple results emit open-preview', async () => {
    const secondItem = {
      ...item,
      drawing_id: 'drawing-2',
      result_id: 'result-2',
      drawing_title: '第二张图纸',
      preview_url: '/results/result-2#page-2',
    }

    const wrapper = mount(SearchResultList, {
      props: {
        items: [item, secondItem],
        total: 2,
        query: 'fan',
        retrievalMode: 'hybrid',
        loading: false,
      },
      global: {
        stubs: {
          SearchResultCard: {
            props: ['item', 'index'],
            emits: ['open-preview'],
            template: `
              <button
                type="button"
                :data-action="'open-preview-' + index"
                @click="$emit('open-preview')"
              >
                {{ item.drawing_title }}
              </button>
            `,
          },
        },
      },
    })

    await wrapper.find('[data-action="open-preview-1"]').trigger('click')

    expect(wrapper.emitted('open-preview')).toEqual([[secondItem]])
  })
})
