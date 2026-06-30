import { buildApiUrl, normalizeError, parseJsonBody } from './http'
import type {
  AnalyzeResponse,
  ResultDetail,
  ResultError,
  ResultManifest,
  ResultSteps,
} from '../types/results'

export async function submitAnalyze(file: File, fetchImpl = fetch): Promise<AnalyzeResponse> {
  const formData = new FormData()
  formData.append('drawing', file, file.name)
  const response = await fetchImpl(buildApiUrl('/analyze'), {
    method: 'POST',
    body: formData,
  })
  const body = await parseJsonBody(response)
  if (!response.ok) throw new Error(normalizeError(body, '提交分析任务失败'))
  return body as AnalyzeResponse
}

export async function getResult(resultId: string, fetchImpl = fetch): Promise<ResultDetail> {
  const response = await fetchImpl(buildApiUrl(`/api/results/${resultId}`))
  const body = await parseJsonBody(response)
  if (!response.ok) throw new Error(normalizeError(body, '获取结果失败'))
  return body as ResultDetail
}

export async function getResultSteps(resultId: string, fetchImpl = fetch): Promise<ResultSteps> {
  const response = await fetchImpl(buildApiUrl(`/api/results/${resultId}/steps`))
  const body = await parseJsonBody(response)
  if (!response.ok) throw new Error(normalizeError(body, '获取步骤失败'))
  return body as ResultSteps
}

export async function getResultManifest(resultId: string, fetchImpl = fetch): Promise<ResultManifest> {
  const response = await fetchImpl(buildApiUrl(`/api/results/${resultId}/manifest`))
  const body = await parseJsonBody(response)
  if (!response.ok) throw new Error(normalizeError(body, '获取清单失败'))
  return body as ResultManifest
}

export async function getResultError(resultId: string, fetchImpl = fetch): Promise<ResultError> {
  const response = await fetchImpl(buildApiUrl(`/api/results/${resultId}/error`))
  const body = await parseJsonBody(response)
  if (!response.ok) throw new Error(normalizeError(body, '获取错误信息失败'))
  return body as ResultError
}
