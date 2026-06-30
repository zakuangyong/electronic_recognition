import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { flushPromises } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import SearchView from '../SearchView.vue'

function createTestRouter() {
  return createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/', redirect: '/workbench' },
      { path: '/workbench', component: { template: '<div>Workbench</div>' } },
      { path: '/search', component: SearchView },
      { path: '/knowledge', component: { template: '<div>Knowledge</div>' } },
      { path: '/results/:resultId', component: { template: '<div>Result</div>' } },
      { path: '/drawing-diff', component: { template: '<div>Diff</div>' } },
    ],
  })
}

describe('SearchView', () => {
  beforeEach(() => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/search/health')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () =>
            Promise.resolve(
              JSON.stringify({
                enabled: true,
                degraded: false,
                status: 'ok',
                mode: 'hybrid',
                indexed_drawings: 0,
                indexed_chunks: 0,
                vector_points: 0,
                failed_jobs: 0,
                sqlite_available: true,
                embedding_backend_available: false,
                qdrant_available: false,
              }),
            ),
        })
      }

      if (url.endsWith('/api/search/demo-queries')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () =>
            Promise.resolve(
              JSON.stringify({
                exact: [
                  {
                    query: 'A17387',
                    type: 'exact',
                    notes: 'demo',
                  },
                ],
              }),
            ),
        })
      }

      if (url.endsWith('/api/search/rebuild')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () => Promise.resolve(JSON.stringify({ indexed: 0 })),
        })
      }

      if (url.endsWith('/api/search')) {
        const body = init?.body ? JSON.parse(String(init.body)) : {}
        if (body.debug !== true && body.debug !== false) {
          return Promise.resolve({
            ok: false,
            status: 400,
            text: () => Promise.resolve(JSON.stringify({ detail: 'bad payload' })),
          })
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () =>
            Promise.resolve(
              JSON.stringify({
                query: { raw: body.query },
                total: 1,
                items: [
                  {
                    drawing_id: 'drawing-1',
                    result_id: 'result-1',
                    filename: 'demo.pdf',
                    drawing_number: 'A17387_1706',
                    drawing_title: '风机控制图',
                    revision: 'B',
                    project_name: 'Project',
                    system_name: 'System',
                    score: 0.88,
                    matched_pages: [1],
                    matched_components: ['KM1'],
                    matched_combinations: [],
                    matched_chunk_types: ['drawing'],
                    snippet: 'snippet',
                    match_sources: ['bm25'],
                    preview_url: '/results/result-1#page-1',
                    source_hash: '',
                    collapsed_versions: 0,
                    history_versions: [],
                    debug: { hits: [] },
                  },
                ],
                retrieval_mode: body.retrieval_mode || 'hybrid',
                degraded: false,
              }),
            ),
        })
      }

      return Promise.resolve({
        ok: false,
        status: 404,
        text: () => Promise.resolve(JSON.stringify({ detail: 'not found' })),
      })
    })

    vi.stubGlobal('fetch', fetchMock)
  })

  it('renders option c refined search shell', async () => {
    const router = createTestRouter()
    await router.push('/search')
    await router.isReady()

    const wrapper = mount(SearchView, {
      global: { plugins: [router] },
    })

    expect(wrapper.find('.topbar.topbar--dark').exists()).toBe(true)
    expect(wrapper.find('.diff-a-shell').exists()).toBe(true)
    expect(wrapper.find('.diff-a-board').exists()).toBe(true)
    expect(wrapper.text()).toContain('检索条件')
    expect(wrapper.text()).toContain('查询结果')
    expect(wrapper.find('[data-capability="save-query"]').attributes('disabled')).toBeDefined()
  })

  it('does not expose retrieval mode options (BM25 only)', () => {
    const router = createTestRouter()
    router.push('/search')

    const wrapper = mount(SearchView, {
      global: { plugins: [router] },
    })

    expect(wrapper.find('.search-mode-group').exists()).toBe(false)
    expect(wrapper.findAll('input[type="radio"]').length).toBe(0)
  })

  it('renders navigation links', () => {
    const router = createTestRouter()
    router.push('/search')

    const wrapper = mount(SearchView, {
      global: { plugins: [router] },
    })

    const links = wrapper.findAll('a.chip')
    expect(links.length).toBeGreaterThanOrEqual(1)
  })

  it('uses option c refined screen hierarchy', () => {
    const router = createTestRouter()
    router.push('/search')

    const wrapper = mount(SearchView, {
      global: { plugins: [router] },
    })

    expect(wrapper.find('.topbar.topbar--dark').exists()).toBe(true)
    expect(wrapper.find('.diff-a-shell').exists()).toBe(true)
    expect(wrapper.find('.diff-a-topbar .diff-a-meta').exists()).toBe(true)
    expect(wrapper.find('.diff-a-board').exists()).toBe(true)
  })

  it('submits search request and renders result items', async () => {
    const router = createTestRouter()
    await router.push('/search')
    await router.isReady()

    const wrapper = mount(SearchView, {
      global: { plugins: [router] },
    })

    await flushPromises()

    const queryInput = wrapper.find('input[type="search"]')
    await queryInput.setValue('thermal overload fan')
    await wrapper.find('form.search-form').trigger('submit')

    await flushPromises()

    expect(String((globalThis.fetch as unknown as any).mock.calls[0][0])).toContain(
      '/api/search/health',
    )

    const searchCalls = (globalThis.fetch as unknown as any).mock.calls.filter(
      (call: any[]) => String(call[0]).endsWith('/api/search'),
    )
    expect(searchCalls.length).toBeGreaterThanOrEqual(1)
    expect(wrapper.text()).toContain('风机控制图')
    expect(wrapper.text()).toContain('打开图纸')
    expect(wrapper.text()).not.toContain('查看结果')
  })

  it('renders query result header instead of shell metrics after search', async () => {
    const router = createTestRouter()
    await router.push('/search')
    await router.isReady()

    const wrapper = mount(SearchView, {
      global: { plugins: [router] },
    })

    await flushPromises()
    await wrapper.find('input[type="search"]').setValue('thermal overload fan')
    await wrapper.find('form.search-form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('查询')
    expect(wrapper.text()).toContain('thermal overload fan')
    expect(wrapper.text()).toContain('找到 1 条结果')
    expect(wrapper.text()).toContain('排序')
    expect(wrapper.text()).not.toContain('目标区域')
    expect(wrapper.text()).not.toContain('主结果区')
    expect(wrapper.text()).not.toContain('standard')
  })

  it('replaces legacy result action copy and shell labels', async () => {
    const router = createTestRouter()
    await router.push('/search')
    await router.isReady()

    const wrapper = mount(SearchView, {
      global: { plugins: [router] },
    })

    await flushPromises()
    await wrapper.find('input[type="search"]').setValue('thermal overload fan')
    await wrapper.find('form.search-form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('打开图纸')
    expect(wrapper.text()).toContain('命中理由')
    expect(wrapper.text()).not.toContain('查看结果')
    expect(wrapper.text()).not.toContain('目标区域')
    expect(wrapper.text()).not.toContain('query')
    expect(wrapper.text()).not.toContain('等待输入 query')
  })

  it('renders trimmed lastQuery in result header after search', async () => {
    const router = createTestRouter()
    await router.push('/search')
    await router.isReady()

    const wrapper = mount(SearchView, {
      global: { plugins: [router] },
    })

    await flushPromises()
    await wrapper.find('input[type="search"]').setValue('  thermal overload fan  ')
    await wrapper.find('form.search-form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('查询：thermal overload fan')
    expect(wrapper.text()).not.toContain('查询：  thermal overload fan  ')
  })

  it('always searches with BM25 retrieval mode', async () => {
    const router = createTestRouter()
    await router.push('/search')
    await router.isReady()

    const wrapper = mount(SearchView, {
      global: { plugins: [router] },
    })

    await flushPromises()
    await wrapper.find('input[type="search"]').setValue('thermal overload fan')
    await wrapper.find('form.search-form').trigger('submit')
    await flushPromises()

    const searchCalls = (globalThis.fetch as unknown as any).mock.calls.filter(
      (call: any[]) => String(call[0]).endsWith('/api/search'),
    )
    const lastPayload = JSON.parse(String(searchCalls.at(-1)?.[1]?.body ?? '{}'))

    expect(lastPayload.retrieval_mode).toBe('bm25')
    expect(wrapper.text()).toContain('模式 bm25')
  })

  it('keeps latest search result when an older response resolves later', async () => {
    const router = createTestRouter()
    await router.push('/search')
    await router.isReady()

    let resolveFirst: ((value: any) => void) | undefined
    let resolveSecond: ((value: any) => void) | undefined

    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/search/health')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () =>
            Promise.resolve(
              JSON.stringify({
                enabled: true,
                degraded: false,
                status: 'ok',
                mode: 'hybrid',
                indexed_drawings: 0,
                indexed_chunks: 0,
                vector_points: 0,
                failed_jobs: 0,
                sqlite_available: true,
                embedding_backend_available: false,
                qdrant_available: false,
              }),
            ),
        })
      }

      if (url.endsWith('/api/search')) {
        const body = init?.body ? JSON.parse(String(init.body)) : {}
        if (body.query === 'first query') {
          return new Promise((resolve) => {
            resolveFirst = resolve
          })
        }
        if (body.query === 'second query') {
          return new Promise((resolve) => {
            resolveSecond = resolve
          })
        }
      }

      return Promise.resolve({
        ok: false,
        status: 404,
        text: () => Promise.resolve(JSON.stringify({ detail: 'not found' })),
      })
    })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SearchView, {
      global: { plugins: [router] },
    })

    await flushPromises()

    const queryInput = wrapper.find('input[type="search"]')
    await queryInput.setValue('first query')
    await wrapper.find('form.search-form').trigger('submit')
    await queryInput.setValue('second query')
    await wrapper.find('form.search-form').trigger('submit')

    resolveSecond?.({
      ok: true,
      status: 200,
      text: () =>
        Promise.resolve(
          JSON.stringify({
            query: { raw: 'second query' },
            total: 1,
            items: [
              {
                drawing_id: 'drawing-2',
                result_id: 'result-2',
                filename: 'second.pdf',
                drawing_number: 'B200',
                drawing_title: '第二次结果',
                revision: 'A',
                project_name: 'Project',
                system_name: 'System',
                score: 0.91,
                matched_pages: [2],
                matched_components: ['QF1'],
                matched_combinations: [],
                matched_chunk_types: ['drawing'],
                snippet: 'second snippet',
                match_sources: ['bm25'],
                preview_url: '/results/result-2#page-2',
                source_hash: '',
                collapsed_versions: 0,
                history_versions: [],
                debug: { hits: [] },
              },
            ],
            retrieval_mode: 'hybrid',
            degraded: false,
          }),
        ),
    })
    await flushPromises()

    resolveFirst?.({
      ok: true,
      status: 200,
      text: () =>
        Promise.resolve(
          JSON.stringify({
            query: { raw: 'first query' },
            total: 1,
            items: [
              {
                drawing_id: 'drawing-1',
                result_id: 'result-1',
                filename: 'first.pdf',
                drawing_number: 'A100',
                drawing_title: '第一次结果',
                revision: 'A',
                project_name: 'Project',
                system_name: 'System',
                score: 0.87,
                matched_pages: [1],
                matched_components: ['KM1'],
                matched_combinations: [],
                matched_chunk_types: ['drawing'],
                snippet: 'first snippet',
                match_sources: ['bm25'],
                preview_url: '/results/result-1#page-1',
                source_hash: '',
                collapsed_versions: 0,
                history_versions: [],
                debug: { hits: [] },
              },
            ],
            retrieval_mode: 'hybrid',
            degraded: false,
          }),
        ),
    })
    await flushPromises()

    expect(wrapper.text()).toContain('查询：second query')
    expect(wrapper.text()).toContain('第二次结果')
    expect(wrapper.text()).not.toContain('第一次结果')
  })

  it('shows no-result copy instead of waiting state after a 0-hit search', async () => {
    const router = createTestRouter()
    await router.push('/search')
    await router.isReady()

    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/search/health')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () =>
            Promise.resolve(
              JSON.stringify({
                enabled: true,
                degraded: false,
                status: 'ok',
                mode: 'hybrid',
                indexed_drawings: 0,
                indexed_chunks: 0,
                vector_points: 0,
                failed_jobs: 0,
                sqlite_available: true,
                embedding_backend_available: false,
                qdrant_available: false,
              }),
            ),
        })
      }

      if (url.endsWith('/api/search')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () =>
            Promise.resolve(
              JSON.stringify({
                query: { raw: 'missing drawing' },
                total: 0,
                items: [],
                retrieval_mode: 'hybrid',
                degraded: false,
              }),
            ),
        })
      }

      return Promise.resolve({
        ok: false,
        status: 404,
        text: () => Promise.resolve(JSON.stringify({ detail: 'not found' })),
      })
    })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SearchView, {
      global: { plugins: [router] },
    })

    await flushPromises()
    await wrapper.find('input[type="search"]').setValue('missing drawing')
    await wrapper.find('form.search-form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('查询：missing drawing')
    expect(wrapper.text()).toContain('找到 0 条结果')
    expect(wrapper.text()).toContain('未找到匹配结果')
    expect(wrapper.text()).not.toContain('等待检索')
  })

  it('does not let a stale failed response pollute the latest successful UI', async () => {
    const router = createTestRouter()
    await router.push('/search')
    await router.isReady()

    let resolveSuccess: ((value: any) => void) | undefined
    let resolveFailure: ((value: any) => void) | undefined

    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/search/health')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () =>
            Promise.resolve(
              JSON.stringify({
                enabled: true,
                degraded: false,
                status: 'ok',
                mode: 'hybrid',
                indexed_drawings: 0,
                indexed_chunks: 0,
                vector_points: 0,
                failed_jobs: 0,
                sqlite_available: true,
                embedding_backend_available: false,
                qdrant_available: false,
              }),
            ),
        })
      }

      if (url.endsWith('/api/search')) {
        const body = init?.body ? JSON.parse(String(init.body)) : {}
        if (body.query === 'older query') {
          return new Promise((resolve) => {
            resolveFailure = resolve
          })
        }
        if (body.query === 'latest query') {
          return new Promise((resolve) => {
            resolveSuccess = resolve
          })
        }
      }

      return Promise.resolve({
        ok: false,
        status: 404,
        text: () => Promise.resolve(JSON.stringify({ detail: 'not found' })),
      })
    })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SearchView, {
      global: { plugins: [router] },
    })

    await flushPromises()

    const queryInput = wrapper.find('input[type="search"]')
    await queryInput.setValue('older query')
    await wrapper.find('form.search-form').trigger('submit')
    await queryInput.setValue('latest query')
    await wrapper.find('form.search-form').trigger('submit')

    resolveSuccess?.({
      ok: true,
      status: 200,
      text: () =>
        Promise.resolve(
          JSON.stringify({
            query: { raw: 'latest query' },
            total: 1,
            items: [
              {
                drawing_id: 'drawing-latest',
                result_id: 'result-latest',
                filename: 'latest.pdf',
                drawing_number: 'L100',
                drawing_title: '最新结果',
                revision: 'A',
                project_name: 'Project',
                system_name: 'System',
                score: 0.95,
                matched_pages: [2],
                matched_components: ['KA1'],
                matched_combinations: [],
                matched_chunk_types: ['drawing'],
                snippet: 'latest snippet',
                match_sources: ['bm25'],
                preview_url: '/results/result-latest#page-2',
                source_hash: '',
                collapsed_versions: 0,
                history_versions: [],
                debug: { hits: [] },
              },
            ],
            retrieval_mode: 'hybrid',
            degraded: false,
          }),
        ),
    })
    await flushPromises()

    resolveFailure?.({
      ok: false,
      status: 500,
      text: () => Promise.resolve(JSON.stringify({ detail: 'stale failed response' })),
    })
    await flushPromises()

    expect(wrapper.text()).toContain('查询：latest query')
    expect(wrapper.text()).toContain('最新结果')
    expect(wrapper.text()).not.toContain('stale failed response')
    expect(wrapper.text()).not.toContain('检索失败')
  })

  it('shows loading empty state before a 0-hit response arrives', async () => {
    const router = createTestRouter()
    await router.push('/search')
    await router.isReady()

    let resolveSearch: ((value: any) => void) | undefined

    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/search/health')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () =>
            Promise.resolve(
              JSON.stringify({
                enabled: true,
                degraded: false,
                status: 'ok',
                mode: 'hybrid',
                indexed_drawings: 0,
                indexed_chunks: 0,
                vector_points: 0,
                failed_jobs: 0,
                sqlite_available: true,
                embedding_backend_available: false,
                qdrant_available: false,
              }),
            ),
        })
      }

      if (url.endsWith('/api/search')) {
        return new Promise((resolve) => {
          resolveSearch = resolve
        })
      }

      return Promise.resolve({
        ok: false,
        status: 404,
        text: () => Promise.resolve(JSON.stringify({ detail: 'not found' })),
      })
    })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SearchView, {
      global: { plugins: [router] },
    })

    await flushPromises()
    await wrapper.find('input[type="search"]').setValue('pending query')
    await wrapper.find('form.search-form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('查询：pending query')
    expect(wrapper.text()).toContain('正在检索')
    expect(wrapper.text()).not.toContain('未找到匹配结果')
    expect(wrapper.text()).not.toContain('等待检索')

    resolveSearch?.({
      ok: true,
      status: 200,
      text: () =>
        Promise.resolve(
          JSON.stringify({
            query: { raw: 'pending query' },
            total: 0,
            items: [],
            retrieval_mode: 'hybrid',
            degraded: false,
          }),
        ),
    })
    await flushPromises()
  })

  it('clears stale result list when a new query starts', async () => {
    const router = createTestRouter()
    await router.push('/search')
    await router.isReady()

    let resolveNextSearch: ((value: any) => void) | undefined

    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/search/health')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () =>
            Promise.resolve(
              JSON.stringify({
                enabled: true,
                degraded: false,
                status: 'ok',
                mode: 'hybrid',
                indexed_drawings: 0,
                indexed_chunks: 0,
                vector_points: 0,
                failed_jobs: 0,
                sqlite_available: true,
                embedding_backend_available: false,
                qdrant_available: false,
              }),
            ),
        })
      }

      if (url.endsWith('/api/search')) {
        const body = init?.body ? JSON.parse(String(init.body)) : {}
        if (body.query === 'first query') {
          return Promise.resolve({
            ok: true,
            status: 200,
            text: () =>
              Promise.resolve(
                JSON.stringify({
                  query: { raw: 'first query' },
                  total: 1,
                  items: [
                    {
                      drawing_id: 'drawing-first',
                      result_id: 'result-first',
                      filename: 'first.pdf',
                      drawing_number: 'F100',
                      drawing_title: '第一次列表结果',
                      revision: 'A',
                      project_name: 'Project',
                      system_name: 'System',
                      score: 0.82,
                      matched_pages: [1],
                      matched_components: ['KM1'],
                      matched_combinations: [],
                      matched_chunk_types: ['drawing'],
                      snippet: 'first snippet',
                      match_sources: ['bm25'],
                      preview_url: '/results/result-first#page-1',
                      source_hash: '',
                      collapsed_versions: 0,
                      history_versions: [],
                      debug: { hits: [] },
                    },
                  ],
                  retrieval_mode: 'hybrid',
                  degraded: false,
                }),
              ),
          })
        }

        if (body.query === 'second query') {
          return new Promise((resolve) => {
            resolveNextSearch = resolve
          })
        }
      }

      return Promise.resolve({
        ok: false,
        status: 404,
        text: () => Promise.resolve(JSON.stringify({ detail: 'not found' })),
      })
    })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SearchView, {
      global: { plugins: [router] },
    })

    await flushPromises()

    const queryInput = wrapper.find('input[type="search"]')
    await queryInput.setValue('first query')
    await wrapper.find('form.search-form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('查询：first query')
    expect(wrapper.text()).toContain('第一次列表结果')

    await queryInput.setValue('second query')
    await wrapper.find('form.search-form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('查询：second query')
    expect(wrapper.text()).toContain('正在检索')
    expect(wrapper.text()).not.toContain('第一次列表结果')

    resolveNextSearch?.({
      ok: true,
      status: 200,
      text: () =>
        Promise.resolve(
          JSON.stringify({
            query: { raw: 'second query' },
            total: 0,
            items: [],
            retrieval_mode: 'hybrid',
            degraded: false,
          }),
        ),
    })
    await flushPromises()
  })

  it('opens drawing preview modal from result action', async () => {
    const router = createTestRouter()
    await router.push('/search')
    await router.isReady()

    const wrapper = mount(SearchView, {
      global: { plugins: [router] },
      attachTo: document.body,
    })

    await flushPromises()
    await wrapper.find('input[type="search"]').setValue('thermal overload fan')
    await wrapper.find('form.search-form').trigger('submit')
    await flushPromises()

    await wrapper.find('[data-action="open-preview"]').trigger('click')

    expect(document.body.textContent).toContain('打开图纸预览')
    expect(document.body.textContent).toContain('第 1 页')
  })

  it('updates right preview panel when clicking a result card', async () => {
    const router = createTestRouter()
    await router.push('/search')
    await router.isReady()

    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/search/health')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () =>
            Promise.resolve(
              JSON.stringify({
                enabled: true,
                degraded: false,
                status: 'ok',
                mode: 'hybrid',
                indexed_drawings: 0,
                indexed_chunks: 0,
                vector_points: 0,
                failed_jobs: 0,
                sqlite_available: true,
                embedding_backend_available: false,
                qdrant_available: false,
              }),
            ),
        })
      }

      if (url.endsWith('/api/search/demo-queries')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () => Promise.resolve(JSON.stringify({ exact: [] })),
        })
      }

      if (url.endsWith('/api/search')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: () =>
            Promise.resolve(
              JSON.stringify({
                query: { raw: 'km1' },
                total: 2,
                items: [
                  {
                    drawing_id: 'drawing-1',
                    result_id: 'result-1',
                    filename: 'first.pdf',
                    drawing_number: 'A100',
                    drawing_title: '第一次结果',
                    revision: 'A',
                    project_name: 'Project',
                    system_name: 'System',
                    score: 0.87,
                    matched_pages: [1],
                    matched_components: ['KM1'],
                    matched_combinations: [],
                    matched_chunk_types: ['drawing'],
                    snippet: 'first snippet',
                    match_sources: ['bm25'],
                    preview_url: '/results/result-1#page-1',
                    source_hash: '',
                    collapsed_versions: 0,
                    history_versions: [],
                    debug: { hits: [] },
                  },
                  {
                    drawing_id: 'drawing-2',
                    result_id: 'result-2',
                    filename: 'second.pdf',
                    drawing_number: 'B200',
                    drawing_title: '第二次结果',
                    revision: 'B',
                    project_name: 'Project',
                    system_name: 'System',
                    score: 0.91,
                    matched_pages: [2],
                    matched_components: ['QF1'],
                    matched_combinations: [],
                    matched_chunk_types: ['drawing'],
                    snippet: 'second snippet',
                    match_sources: ['bm25'],
                    preview_url: '/results/result-2#page-2',
                    source_hash: '',
                    collapsed_versions: 0,
                    history_versions: [],
                    debug: { hits: [] },
                  },
                ],
                retrieval_mode: 'hybrid',
                degraded: false,
              }),
            ),
        })
      }

      return Promise.resolve({
        ok: false,
        status: 404,
        text: () => Promise.resolve(JSON.stringify({ detail: 'not found' })),
      })
    })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SearchView, {
      global: { plugins: [router] },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('等待选择')

    await wrapper.find('input[type="search"]').setValue('km1')
    await wrapper.find('form.search-form').trigger('submit')
    await flushPromises()

    const cards = wrapper.findAll('.search-result-item')
    expect(cards.length).toBeGreaterThanOrEqual(2)

    await cards[1].trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('第二次结果')
  })

  it('triggers rebuild action from search toolbar', async () => {
    const router = createTestRouter()
    await router.push('/search')
    await router.isReady()

    const wrapper = mount(SearchView, {
      global: { plugins: [router] },
    })

    await flushPromises()

    await wrapper.find('button[data-action="rebuild-index"]').trigger('click')
    await flushPromises()

    const rebuildCalls = (globalThis.fetch as unknown as any).mock.calls.filter(
      (call: any[]) => String(call[0]).endsWith('/api/search/rebuild'),
    )
    expect(rebuildCalls.length).toBeGreaterThanOrEqual(1)
    expect(wrapper.text()).toContain('索引重建任务已触发')
  })
})
