import { buildApiUrl, normalizeError, parseJsonBody } from './http'
import type { ComponentItem, RuleItem } from '../types/knowledge'

export async function fetchKnowledge(fetchImpl = fetch): Promise<{ count: number; items: ComponentItem[] }> {
  const response = await fetchImpl(buildApiUrl('/api/knowledge'))
  const body = await parseJsonBody(response)
  if (!response.ok) throw new Error(normalizeError(body, '知识库加载失败'))
  return body as { count: number; items: ComponentItem[] }
}

export async function fetchCustomRules(fetchImpl = fetch): Promise<{ count: number; items: RuleItem[] }> {
  const response = await fetchImpl(buildApiUrl('/api/custom-rules'))
  const body = await parseJsonBody(response)
  if (!response.ok) throw new Error(normalizeError(body, '规则库加载失败'))
  return body as { count: number; items: RuleItem[] }
}

export async function getComponent(componentId: string, fetchImpl = fetch): Promise<ComponentItem> {
  const response = await fetchImpl(buildApiUrl(`/api/knowledge/${componentId}`))
  const body = await parseJsonBody(response)
  if (!response.ok) throw new Error(normalizeError(body, '组件加载失败'))
  return body as ComponentItem
}

export async function getRule(ruleId: string, fetchImpl = fetch): Promise<RuleItem> {
  const response = await fetchImpl(buildApiUrl(`/api/custom-rules/${ruleId}`))
  const body = await parseJsonBody(response)
  if (!response.ok) throw new Error(normalizeError(body, '规则加载失败'))
  return body as RuleItem
}

export async function createComponent(payload: Record<string, unknown>, fetchImpl = fetch): Promise<ComponentItem> {
  const response = await fetchImpl(buildApiUrl('/api/knowledge'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const body = await parseJsonBody(response)
  if (!response.ok) throw new Error(normalizeError(body, '创建组件失败'))
  return body as ComponentItem
}

export async function updateComponent(componentId: string, payload: Record<string, unknown>, fetchImpl = fetch): Promise<ComponentItem> {
  const response = await fetchImpl(buildApiUrl(`/api/knowledge/${componentId}`), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const body = await parseJsonBody(response)
  if (!response.ok) throw new Error(normalizeError(body, '更新组件失败'))
  return body as ComponentItem
}

export async function deleteComponent(componentId: string, fetchImpl = fetch): Promise<{ ok: boolean }> {
  const response = await fetchImpl(buildApiUrl(`/api/knowledge/${componentId}`), { method: 'DELETE' })
  const body = await parseJsonBody(response)
  if (!response.ok) throw new Error(normalizeError(body, '删除组件失败'))
  return body as { ok: boolean }
}

export async function createRule(payload: Record<string, unknown>, fetchImpl = fetch): Promise<RuleItem> {
  const response = await fetchImpl(buildApiUrl('/api/custom-rules'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const body = await parseJsonBody(response)
  if (!response.ok) throw new Error(normalizeError(body, '创建规则失败'))
  return body as RuleItem
}

export async function updateRule(ruleId: string, payload: Record<string, unknown>, fetchImpl = fetch): Promise<RuleItem> {
  const response = await fetchImpl(buildApiUrl(`/api/custom-rules/${ruleId}`), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const body = await parseJsonBody(response)
  if (!response.ok) throw new Error(normalizeError(body, '更新规则失败'))
  return body as RuleItem
}

export async function deleteRule(ruleId: string, fetchImpl = fetch): Promise<{ ok: boolean }> {
  const response = await fetchImpl(buildApiUrl(`/api/custom-rules/${ruleId}`), { method: 'DELETE' })
  const body = await parseJsonBody(response)
  if (!response.ok) throw new Error(normalizeError(body, '删除规则失败'))
  return body as { ok: boolean }
}

export async function uploadComponentImage(
  componentId: string,
  file: File | Blob,
  filename: string,
  kind: string = 'variant',
  fetchImpl = fetch,
): Promise<ComponentItem> {
  const formData = new FormData()
  formData.append('file', file, filename)
  formData.append('kind', kind)
  const response = await fetchImpl(buildApiUrl(`/api/knowledge/${componentId}/images`), {
    method: 'POST',
    body: formData,
  })
  const body = await parseJsonBody(response)
  if (!response.ok) throw new Error(normalizeError(body, '上传图片失败'))
  return body as ComponentItem
}

export async function uploadRuleImage(
  ruleId: string,
  file: File | Blob,
  filename: string,
  fetchImpl = fetch,
): Promise<RuleItem> {
  const formData = new FormData()
  formData.append('file', file, filename)
  const response = await fetchImpl(buildApiUrl(`/api/custom-rules/${ruleId}/image`), {
    method: 'POST',
    body: formData,
  })
  const body = await parseJsonBody(response)
  if (!response.ok) throw new Error(normalizeError(body, '上传图片失败'))
  return body as RuleItem
}

export async function validateRule(
  payload: Record<string, unknown>,
  fetchImpl = fetch,
): Promise<{ valid: boolean; summary?: Record<string, unknown>; warnings?: string[] }> {
  const response = await fetchImpl(buildApiUrl('/api/custom-rules/validate'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const body = await parseJsonBody(response)
  if (!response.ok) throw new Error(normalizeError(body, '规则校验失败'))
  return body as { valid: boolean; summary?: Record<string, unknown>; warnings?: string[] }
}

export async function testRule(
  payload: {
    rule: Record<string, unknown>
    detected_components?: Array<Record<string, unknown>>
    open_symbols?: Array<Record<string, unknown>>
  },
  fetchImpl = fetch,
): Promise<{ matches: Array<Record<string, unknown>> }> {
  const response = await fetchImpl(buildApiUrl('/api/custom-rules/test'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const body = await parseJsonBody(response)
  if (!response.ok) throw new Error(normalizeError(body, '规则试运行失败'))
  return body as { matches: Array<Record<string, unknown>> }
}
