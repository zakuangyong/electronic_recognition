export interface ComponentItem {
  id: string
  label: string
  image_path: string
  image_url: string
  variant_images: string[]
  variant_image_urls: string[]
  component_type: string
  model: string
  definition: string
  standards: string[]
  aliases: string[]
  notes: string
  source: string
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface RuleItem {
  id: string
  name: string
  description: string
  image_path: string
  image_url: string
  engine: string
  enabled: boolean
  scope: string
  confidence: number
  aliases: string[]
  notes: string
  source: string
  member_count: number
  members: RuleMember[]
  created_at: string
  updated_at: string
}

export interface RuleMember {
  role: string
  min_quantity: number
  component_ids: string[]
  code_patterns: string[]
  label_keywords: string[]
}

export interface KnowledgeCatalog {
  components: ComponentItem[]
  rules: RuleItem[]
}
