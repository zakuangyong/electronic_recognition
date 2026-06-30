import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import DrawingPreview from '../DrawingPreview.vue'
import ResultTabs from '../ResultTabs.vue'
import TaskStatusCard from '../TaskStatusCard.vue'
import WorkbenchPreviewTabs from '../WorkbenchPreviewTabs.vue'

describe('recognition display states', () => {
  it('shows animated loading panels while recognition is running', () => {
    const tabs = mount(ResultTabs, {
      props: {
        components: [],
        combinations: [],
        previewPages: [],
        activeTab: 'components',
        loading: true,
      },
    })

    const status = mount(TaskStatusCard, {
      props: {
        components: [],
        loading: true,
      },
    })

    expect(tabs.find('.recognition-loading-panel').exists()).toBe(true)
    expect(tabs.find('.recognition-loader').exists()).toBe(true)
    expect(status.find('.component-list-loading').exists()).toBe(true)
    expect(status.find('.recognition-loader').exists()).toBe(true)
  })

  it('renders extra preview tabs and shows empty states', async () => {
    const wrapper = mount(ResultTabs, {
      props: {
        components: [],
        combinations: [],
        previewPages: [],
        activeTab: 'tag-table',
        componentTable: {},
        controlSignalConfiguration: {},
        titleBlock: {},
      },
    })

    expect(wrapper.text()).toContain('图纸标签表')
    expect(wrapper.text()).toContain('控制/信号信息')
    expect(wrapper.text()).toContain('图签信息')
    expect(wrapper.text()).toContain('暂无图纸标签表')
  })

  it('renders title block fields as key value table', () => {
    const wrapper = mount(ResultTabs, {
      props: {
        components: [],
        combinations: [],
        previewPages: [],
        activeTab: 'title-block',
        titleBlock: {
          fields: {
            客户名称: '某某客户',
            工程名称: '风机控制改造',
          },
          raw: { ignored: true },
        },
      },
    })

    expect(wrapper.text()).toContain('图签信息')
    expect(wrapper.text()).toContain('客户名称')
    expect(wrapper.text()).toContain('某某客户')
    expect(wrapper.text()).toContain('工程名称')
    expect(wrapper.text()).toContain('风机控制改造')
  })

  it('renders drawing boxes without labels and skips table regions', () => {
    const wrapper = mount(DrawingPreview, {
      props: {
        pages: [
          {
            page: 1,
            width: 1000,
            height: 800,
            data_url: 'data:image/png;base64,page-1',
          },
        ],
        components: [
          {
            label: 'Fuse',
            component_type: 'fuse',
            code: 'FU1',
            page: 1,
            regions: [[100, 100, 200, 220]],
            region_type: 'circuit_unknown',
          },
          {
            label: 'Table terminal',
            component_type: 'terminal',
            code: 'X01:1,X01:3,X01:5',
            page: 1,
            regions: [[600, 120, 950, 280]],
            region_type: 'terminal_table',
          },
        ],
      },
    })

    const boxes = wrapper.findAll('.drawing-box')
    expect(boxes).toHaveLength(1)
    expect(wrapper.find('.drawing-box-label').exists()).toBe(false)
    expect(boxes[0].attributes('title')).toBe('FU1')
    expect(wrapper.html()).not.toContain('X01:1,X01:3,X01:5')
  })

  it('renders provided combination annotations instead of component boxes', () => {
    const wrapper = mount(DrawingPreview, {
      props: {
        pages: [
          {
            page: 1,
            width: 1000,
            height: 800,
            data_url: 'data:image/png;base64,page-1',
          },
        ],
        components: [
          {
            label: 'Fuse',
            component_type: 'fuse',
            code: 'FU1',
            page: 1,
            regions: [[100, 100, 200, 220]],
          },
        ],
        annotations: [
          {
            page: 1,
            title: '自定义组合1',
            color: '#2563eb',
            regions: [[80, 80, 280, 260]],
          },
        ],
      },
    })

    const boxes = wrapper.findAll('.drawing-box')
    expect(boxes).toHaveLength(1)
    expect(boxes[0].attributes('title')).toBe('自定义组合1')
  })

  it('fits oversized preview pages and allows zooming below 100%', async () => {
    const widthSpy = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(600)
    const heightSpy = vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(400)

    const wrapper = mount(DrawingPreview, {
      attachTo: document.body,
      props: {
        pages: [
          {
            page: 1,
            width: 1000,
            height: 800,
            data_url: 'data:image/png;base64,page-1',
          },
        ],
        components: [],
      },
    })

    await nextTick()

    expect(wrapper.find('.drawing-preview-zoom-label').text()).toBe('50%')

    const zoomOut = wrapper.findAll('.mini-button').find((button) => button.text() === '−')
    expect(zoomOut?.attributes('disabled')).toBeUndefined()

    await zoomOut?.trigger('click')
    await nextTick()

    expect(wrapper.find('.drawing-preview-zoom-label').text()).toBe('25%')

    wrapper.unmount()
    widthSpy.mockRestore()
    heightSpy.mockRestore()
  })

  it('uses combination annotations in workbench combination tab preview', () => {
    const wrapper = mount(WorkbenchPreviewTabs, {
      props: {
        activeTab: 'combinations',
        loading: false,
        previewPages: [
          {
            page: 1,
            width: 1000,
            height: 800,
            data_url: 'data:image/png;base64,page-1',
          },
        ],
        components: [
          {
            label: '接触器',
            component_type: 'relay',
            code: 'KM1',
            page: 1,
            regions: [[100, 100, 180, 180]],
          },
          {
            label: '熔断器',
            component_type: 'fuse',
            code: 'FU1',
            page: 1,
            regions: [[220, 200, 280, 280]],
          },
        ],
        combinations: [
          {
            id: 'combo-1',
            rule_id: 'rule-custom-1',
            name: '自定义组合1',
            rule_layer: 'custom',
            page: 1,
            pages: [1],
            members: [
              { codes: ['KM1'] },
              { codes: ['FU1'] },
            ],
          },
        ],
      },
    })

    const boxes = wrapper.findAll('.drawing-box')
    expect(boxes).toHaveLength(1)
    expect(boxes[0].attributes('title')).toBe('自定义组合1')
  })

  it('keeps long component codes in a truncatable field with full text in title', () => {
    const longCode = 'X01:1,X01:3,X01:5,X01:2,X01:4,X01:6,X01:7,X01:8,X01:9,X01:10'
    const wrapper = mount(TaskStatusCard, {
      props: {
        components: [
          {
            label: '接线端子',
            component_type: 'terminal',
            code: longCode,
            page: 1,
          },
        ],
      },
    })

    const code = wrapper.find('.component-code-text')
    expect(code.exists()).toBe(true)
    expect(code.text()).toBe(longCode)
    expect(code.attributes('title')).toBe(longCode)
  })
})
