import { buildApiUrl, normalizeError, parseJsonBody } from './http'
import type {
  DiffCompareResponse,
  DrawingDiffFileType,
} from '../types/diff'

export interface CompareDrawingsPayload {
  oldFile: File
  newFile: File
  fileType: DrawingDiffFileType
  dpi: number
  threshold: number
}

export async function compareDrawings(
  payload: CompareDrawingsPayload,
  fetchImpl = fetch,
): Promise<DiffCompareResponse> {
  const formData = new FormData()
  formData.append('old_file', payload.oldFile, payload.oldFile.name)
  formData.append('new_file', payload.newFile, payload.newFile.name)
  formData.append('file_type', payload.fileType)
  formData.append('dpi', String(payload.dpi))
  formData.append('threshold', String(payload.threshold))

  const response = await fetchImpl(buildApiUrl('/api/diff/compare'), {
    method: 'POST',
    body: formData,
  })
  const body = await parseJsonBody(response)
  if (!response.ok) {
    throw new Error(normalizeError(body, '图纸比对失败'))
  }
  const result = body as DiffCompareResponse
  if (!result.success) {
    throw new Error(result.message || '图纸比对失败')
  }
  return result
}

export async function fetchDiffResult(
  jobId: string,
  fetchImpl = fetch,
): Promise<DiffCompareResponse> {
  const response = await fetchImpl(buildApiUrl(`/api/diff/results/${jobId}`), {
    cache: 'no-store',
  })
  const body = await parseJsonBody(response)
  if (!response.ok) throw new Error(normalizeError(body, '比对结果读取失败'))
  return body as DiffCompareResponse
}
