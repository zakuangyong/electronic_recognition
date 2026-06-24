export type JsonValue = string | number | boolean | null | JsonObject | JsonValue[]

export interface JsonObject {
  [key: string]: JsonValue | unknown
}

export type ResponseLike = Pick<Response, 'ok' | 'text'>

export function buildApiUrl(
  path: string,
  baseUrl = import.meta.env.VITE_API_BASE_URL ?? '',
): string {
  const normalizedBase = baseUrl.replace(/\/$/, '')
  const normalizedPath = path.startsWith('/') ? path : `/${path}`

  return normalizedBase ? `${normalizedBase}${normalizedPath}` : normalizedPath
}

export function normalizeError(payload: unknown, fallback: string): string {
  return readMessage(payload) ?? fallback
}

export async function parseJsonBody(
  response: Pick<ResponseLike, 'text'>,
): Promise<unknown> {
  const rawBody = await response.text()
  const trimmedBody = rawBody.trim()

  if (!trimmedBody) {
    return undefined
  }

  try {
    return JSON.parse(trimmedBody) as unknown
  } catch {
    return undefined
  }
}

function readMessage(payload: unknown): string | undefined {
  if (typeof payload === 'string' && payload.trim()) {
    return payload
  }

  if (!payload || typeof payload !== 'object') {
    return undefined
  }

  const detailMessage = readMessage((payload as { detail?: unknown }).detail)
  if (detailMessage) {
    return detailMessage
  }

  return readMessage((payload as { message?: unknown }).message)
}
