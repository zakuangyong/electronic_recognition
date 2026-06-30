export type DrawingDiffFileType = 'catdrawing' | 'dwg' | 'pdf'

export interface DiffResultSummary {
  old_filename: string
  new_filename: string
  page_count: number
  total_diff_count: number
  status: string
  duration_ms: number | null
}

export interface DiffAnnotatedImage {
  page: number
  image_url: string
}

export interface DiffItem {
  id: string
  page: number
  bbox: number[]
  crop_image_url: string
  old_text: string
  new_text: string
  changed_type: string
}

export interface DiffDownloadLinks {
  summary_json_url: string
  excel_report_url: string
}

export interface DiffResultPayload {
  summary: DiffResultSummary
  annotated_images: DiffAnnotatedImage[]
  diff_items: DiffItem[]
  downloads: DiffDownloadLinks
  artifacts: Record<string, string>
}

export interface DiffCompareResponse {
  success: boolean
  message: string
  stage: string | null
  job_id: string | null
  data: DiffResultPayload | null
  error_code: string | null
}

export interface DiffAllRegionsRegion {
  region_id: number
  bbox_px: number[]
  old_crop: string
  new_crop: string
  old_text: string
  new_text: string
  change_type: string
}

export interface DiffAllRegionsPage {
  page: number
  offset_px: number[]
  width_px: number
  height_px: number
  regions: DiffAllRegionsRegion[]
}
