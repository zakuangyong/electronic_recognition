export interface AnalyzeResponse {
  task_id: string
  result_id: string
  status: string
  result_url: string
  steps_url: string
}

export interface ResultDetail {
  result_id: string
  document: string
  status: string
  detected_components: ComponentData[]
  detected_combinations: CombinationData[]
  title_block: Record<string, unknown>
  control_signal_configuration: Record<string, unknown>
  component_table: Record<string, unknown>
  recognition_steps: Record<string, unknown>
  warnings: string[]
  meta: Record<string, unknown>
  preview_pages: PreviewPage[]
  result_files: Record<string, unknown>
  page_layouts?: unknown[]
  error?: Record<string, unknown>
  manifest?: Record<string, unknown>
}

export interface ResultError {
  result_id: string
  document?: string
  status: string
  failed_at?: string
  error?: {
    type?: string
    message?: string
  }
  step_files?: Record<string, string>
  page_files?: Record<string, string>
  [key: string]: unknown
}

export interface ComponentData {
  /** Knowledge-base reference id (e.g. "C001"). */
  reference_id?: string
  /** On-drawing designation / 元件代号 (e.g. "KM1,KM2"). */
  code?: string
  label: string
  component_type: string
  page: number
  /** Bounding boxes in a 0..1000 normalized coordinate space: [x0, y0, x1, y1]. */
  regions?: number[][]
  occurrence_count?: number
  region_id?: string
  region_type?: string
  evidence?: string
  confidence?: number
  /** Legacy/alternate id field kept for backward compatibility with older payloads. */
  id?: string
  bounds?: number[]
  [key: string]: unknown
}

export interface LogEntry {
  time: string
  stage: string
  level: string
  message: string
}

export interface CombinationData {
  id: string
  rule_id: string
  name: string
  rule_layer: string
  members: unknown[]
  page: number
  evidence?: string
  [key: string]: unknown
}

export interface PreviewAnnotation {
  page: number
  title: string
  color: string
  regions: number[][]
}

export interface PreviewPage {
  page: number
  width: number
  height: number
  data_url: string
}

export interface ResultSteps {
  result_id: string
  status: string
  steps: Record<string, unknown>
  files: Record<string, string>
  missing: string[]
}

export interface ResultManifest {
  result_id: string
  created_at: string
  updated_at: string
  status: string
  document: string
  index_status?: string
  index_error?: string
  [key: string]: unknown
}
