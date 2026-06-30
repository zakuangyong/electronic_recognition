export interface SearchQuery {
  query: string
  limit?: number
  offset?: number
  retrieval_mode?: string
  debug?: boolean
  filters?: {
    revision?: string
    project_name?: string
  }
}

export interface SearchResultItem {
  drawing_id: string
  result_id: string
  filename: string
  drawing_number: string
  drawing_title: string
  revision: string
  project_name: string
  system_name: string
  score: number
  matched_pages: number[]
  matched_components: string[]
  matched_combinations: string[]
  matched_chunk_types: string[]
  snippet: string
  match_sources: string[]
  preview_url?: string
  source_hash: string
  collapsed_versions: number
  history_versions: unknown[]
  debug: Record<string, unknown>
}

export interface SearchResponse {
  query: Record<string, unknown>
  total: number
  items: SearchResultItem[]
  retrieval_mode?: string
  degraded?: boolean
  degraded_reason?: string
  timing_ms?: Record<string, number>
}

export interface HealthStatus {
  enabled: boolean
  degraded: boolean
  status: string
  mode?: string
  indexed_drawings?: number
  indexed_chunks?: number
  vector_points?: number
  failed_jobs?: number
  sqlite_available?: boolean
  database?: string
  embedding_backend_available?: boolean
  qdrant_available?: boolean
  collection?: string
}

export interface DemoQueryGroup {
  [type: string]: DemoQueryItem[]
}

export interface DemoQueryItem {
  query: string
  notes?: string
  type: string
  expected_result_ids?: string[]
}

export interface IndexRebuildPayload {
  force?: boolean
  mode?: string
  result_id?: string
}

export interface IndexRebuildResult {
  indexed?: number
  skipped?: number
  failed?: string[]
  chunks?: number
  vectors?: number
  elapsed_seconds?: number
}
