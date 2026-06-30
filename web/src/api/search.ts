import { buildApiUrl, normalizeError, parseJsonBody } from './http'
import type {
  SearchQuery,
  SearchResponse,
  HealthStatus,
  DemoQueryGroup,
  IndexRebuildPayload,
  IndexRebuildResult,
} from '../types/search'

export async function searchDrawings(
  payload: SearchQuery,
  fetchImpl = fetch,
): Promise<SearchResponse> {
  const response = await fetchImpl(buildApiUrl('/api/search'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: payload.query,
      limit: payload.limit ?? 20,
      offset: payload.offset ?? 0,
      debug: payload.debug ?? false,
      retrieval_mode: payload.retrieval_mode?.trim() || undefined,
      filters: {
        revision: payload.filters?.revision || undefined,
        project_name: payload.filters?.project_name || undefined,
      },
    }),
  })
  const body = await parseJsonBody(response)
  if (!response.ok) throw new Error(normalizeError(body, '检索失败'))
  return body as SearchResponse
}

export async function fetchSearchHealth(
  fetchImpl = fetch,
): Promise<HealthStatus> {
  const response = await fetchImpl(buildApiUrl('/api/search/health'), {
    cache: 'no-store',
  })
  const body = await parseJsonBody(response)
  if (!response.ok)
    throw new Error(normalizeError(body, '索引状态读取失败'))
  return body as HealthStatus
}

export async function fetchDemoQueries(
  fetchImpl = fetch,
): Promise<DemoQueryGroup> {
  const response = await fetchImpl(buildApiUrl('/api/search/demo-queries'), {
    cache: 'no-store',
  })
  const body = await parseJsonBody(response)
  if (!response.ok)
    throw new Error(normalizeError(body, '演示查询集加载失败'))
  return (body || {}) as DemoQueryGroup
}

export async function rebuildIndex(
  payload: IndexRebuildPayload,
  fetchImpl = fetch,
): Promise<IndexRebuildResult> {
  const response = await fetchImpl(buildApiUrl('/api/search/rebuild'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      force: payload.force ?? false,
      mode: payload.mode || 'all',
      result_id: payload.result_id || undefined,
    }),
  })
  const body = await parseJsonBody(response)
  if (!response.ok)
    throw new Error(normalizeError(body, '重建索引失败'))
  return body as IndexRebuildResult
}
