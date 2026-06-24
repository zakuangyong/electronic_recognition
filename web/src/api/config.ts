import {
  buildApiUrl,
  normalizeError,
  parseJsonBody,
  type ResponseLike,
} from './http'
import {
  LAYOUT_ROUTER_MODES,
  RECOGNITION_MODES,
  SEARCH_MODES,
  type AppConfig,
} from '../types/config'

type FetchLike = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<ResponseLike>

const CONFIG_FETCH_ERROR = '配置读取失败'

export async function fetchConfig(fetchImpl: FetchLike = fetch): Promise<AppConfig> {
  const response = await fetchImpl(buildApiUrl('/api/config'))
  const payload = await parseJsonBody(response)

  if (!response.ok) {
    throw new Error(normalizeError(payload, CONFIG_FETCH_ERROR))
  }

  if (!isAppConfig(payload)) {
    throw new Error(CONFIG_FETCH_ERROR)
  }

  return payload
}

function isAppConfig(payload: unknown): payload is AppConfig {
  if (!isRecord(payload)) {
    return false
  }

  return (
    isString(payload.model) &&
    isBoolean(payload.api_key_configured) &&
    isString(payload.knowledge_path) &&
    isNumber(payload.component_count) &&
    isString(payload.custom_rules_path) &&
    isNumber(payload.custom_rule_count) &&
    isNumber(payload.reference_batch_size) &&
    isMode(payload.recognition_mode, RECOGNITION_MODES) &&
    isBoolean(payload.layout_routing_enabled) &&
    isMode(payload.layout_router_mode, LAYOUT_ROUTER_MODES) &&
    isBoolean(payload.search_enabled) &&
    isMode(payload.search_mode, SEARCH_MODES) &&
    isBoolean(payload.search_auto_index) &&
    isNumber(payload.open_recognition_concurrency) &&
    isNumber(payload.correction_batch_size) &&
    isNumber(payload.correction_candidate_limit)
  )
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function isString(value: unknown): value is string {
  return typeof value === 'string'
}

function isBoolean(value: unknown): value is boolean {
  return typeof value === 'boolean'
}

function isNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function isMode<T extends readonly string[]>(
  value: unknown,
  allowedValues: T,
): value is T[number] {
  return typeof value === 'string' && allowedValues.includes(value)
}
