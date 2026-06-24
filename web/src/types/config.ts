export const RECOGNITION_MODES = ['hybrid', 'rag_first', 'vision_first'] as const

export type RecognitionMode = (typeof RECOGNITION_MODES)[number]

export const LAYOUT_ROUTER_MODES = [
  'rules',
  'detector',
  'hybrid',
  'disabled',
] as const

export type LayoutRouterMode = (typeof LAYOUT_ROUTER_MODES)[number]

export const SEARCH_MODES = ['bm25', 'vector', 'hybrid', 'disabled'] as const

export type SearchMode = (typeof SEARCH_MODES)[number]

export interface AppConfig {
  model: string
  api_key_configured: boolean
  knowledge_path: string
  component_count: number
  custom_rules_path: string
  custom_rule_count: number
  reference_batch_size: number
  recognition_mode: RecognitionMode
  layout_routing_enabled: boolean
  layout_router_mode: LayoutRouterMode
  search_enabled: boolean
  search_mode: SearchMode
  search_auto_index: boolean
  open_recognition_concurrency: number
  correction_batch_size: number
  correction_candidate_limit: number
}
