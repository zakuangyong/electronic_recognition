<script setup lang="ts">
import { computed, reactive } from 'vue'
import type { ComponentData, CombinationData, PreviewAnnotation, PreviewPage } from '../../types/results'
import { colorForKey, componentColorKey } from '../../app/componentColors'
import DrawingPreview from './DrawingPreview.vue'

const props = defineProps<{
  components: ComponentData[]
  combinations: CombinationData[]
  previewPages: PreviewPage[]
  activeTab: string
  loading?: boolean
  componentTable?: unknown
  controlSignalConfiguration?: unknown
  titleBlock?: unknown
}>()

const emit = defineEmits<{
  'update:activeTab': [tab: string]
}>()

function switchTab(tab: string) {
  emit('update:activeTab', tab)
}

function designation(comp: ComponentData): string {
  return (comp.code || comp.reference_id || comp.id || '').trim() || '--'
}

function confidencePercent(comp: ComponentData): string | null {
  if (typeof comp.confidence !== 'number') return null
  return `${Math.round(comp.confidence * 100)}%`
}

function colorOf(comp: ComponentData): string {
  return colorForKey(componentColorKey(comp))
}

const tabs = computed(() => [
  { key: 'component-identification', label: '元件标识', count: props.components.length },
  { key: 'combinations', label: '组合', count: props.combinations.length },
  { key: 'tag-table', label: '图纸标签表' },
  { key: 'control-signal', label: '控制/信号信息' },
  { key: 'title-block', label: '图签信息' },
])

function isEmptyPayload(payload: unknown): boolean {
  if (payload == null) return true
  if (Array.isArray(payload)) return payload.length === 0
  if (typeof payload === 'object') return Object.keys(payload as Record<string, unknown>).length === 0
  return false
}

function toPrettyJson(payload: unknown): string {
  return JSON.stringify(payload ?? {}, null, 2)
}

const rawExpanded = reactive<Record<string, boolean>>({
  'tag-table': false,
  'control-signal': false,
  'title-block': false,
})

async function copyJson(payload: unknown) {
  const text = toPrettyJson(payload)
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    void text
  }
}

function normalizeRows(payload: unknown): Array<Record<string, unknown>> | null {
  if (Array.isArray(payload)) {
    return payload.filter((row) => typeof row === 'object' && row !== null) as Array<Record<string, unknown>>
  }
  if (payload && typeof payload === 'object') {
    const asAny = payload as Record<string, unknown>
    const rows = asAny.rows
    if (Array.isArray(rows)) {
      return rows.filter((row) => typeof row === 'object' && row !== null) as Array<Record<string, unknown>>
    }
  }
  return null
}

function tableColumns(rows: Array<Record<string, unknown>>): string[] {
  const first = rows[0]
  if (!first) return []
  return Object.keys(first).slice(0, 7)
}

function kvEntries(payload: unknown): Array<[string, unknown]> {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return []
  return Object.entries(payload as Record<string, unknown>)
}

function titleBlockEntries(payload: unknown): Array<[string, unknown]> {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return []
  const fields = (payload as any).fields
  if (fields && typeof fields === 'object' && !Array.isArray(fields)) {
    return Object.entries(fields as Record<string, unknown>)
  }
  return Object.entries(payload as Record<string, unknown>)
}

const controlSignals = computed(() => {
  const payload = props.controlSignalConfiguration
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return []
  const signals = (payload as any).signals
  return Array.isArray(signals) ? signals : []
})

const controlControls = computed(() => {
  const payload = props.controlSignalConfiguration
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return []
  const controls = (payload as any).controls
  return Array.isArray(controls) ? controls : []
})

function combinationMemberLabel(member: unknown, index: number): string {
  if (typeof member === 'string' || typeof member === 'number') return String(member)
  if (member && typeof member === 'object') {
    const record = member as Record<string, unknown>
    return String(
      record.code
      || record.label
      || record.name
      || record.id
      || record.reference_id
      || `成员 ${index + 1}`,
    )
  }
  return `成员 ${index + 1}`
}

function normalizedCode(value: unknown): string {
  return typeof value === 'string' ? value.trim().toLowerCase() : ''
}

function codeTokens(value: unknown): string[] {
  if (typeof value !== 'string') return []
  return value
    .split(/[\s,，/|+]+/)
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean)
}

function memberCodes(member: unknown): string[] {
  if (!member || typeof member !== 'object') return []
  const record = member as Record<string, unknown>
  const codes = Array.isArray(record.codes) ? record.codes : [record.code]
  return codes
    .flatMap((item) => {
      if (typeof item === 'string') return codeTokens(item)
      if (typeof item === 'number') return [String(item)]
      return []
    })
    .filter(Boolean)
}

function combinationPages(combo: CombinationData): number[] {
  const pages = Array.isArray(combo.pages)
    ? combo.pages.filter((page): page is number => typeof page === 'number')
    : []
  if (pages.length) return pages
  return typeof combo.page === 'number' ? [combo.page] : []
}

function componentMatchesCodes(component: ComponentData, codes: string[]): boolean {
  if (!codes.length) return false
  const candidates = [
    normalizedCode(component.code),
    normalizedCode(component.reference_id),
    normalizedCode(component.id),
  ].filter(Boolean)
  const tokens = [
    ...candidates,
    ...codeTokens(component.code),
    ...codeTokens(component.reference_id),
    ...codeTokens(component.id),
  ]
  return codes.some((code) => tokens.includes(code))
}

function unionRegions(regions: number[][]): number[] | null {
  const validRegions = regions.filter((region) => Array.isArray(region) && region.length === 4)
  if (!validRegions.length) return null
  const [firstX0, firstY0, firstX1, firstY1] = validRegions[0]
  let minX = firstX0
  let minY = firstY0
  let maxX = firstX1
  let maxY = firstY1
  for (const [x0, y0, x1, y1] of validRegions.slice(1)) {
    minX = Math.min(minX, x0)
    minY = Math.min(minY, y0)
    maxX = Math.max(maxX, x1)
    maxY = Math.max(maxY, y1)
  }
  return maxX > minX && maxY > minY ? [minX, minY, maxX, maxY] : null
}

const combinationAnnotations = computed<PreviewAnnotation[]>(() => {
  return props.combinations.flatMap((combo) => {
    const memberCodeSet = new Set(
      (Array.isArray(combo.members) ? combo.members : []).flatMap((member) => memberCodes(member)),
    )
    const codes = Array.from(memberCodeSet)
    if (!codes.length) return []
    return combinationPages(combo).flatMap((page) => {
      const matchedRegions = props.components
        .filter((component) => component.page === page && componentMatchesCodes(component, codes))
        .flatMap((component) => Array.isArray(component.regions) ? component.regions : [])
      const region = unionRegions(matchedRegions)
      if (!region) return []
      return [{
        page,
        title: combo.name || combo.rule_id || combo.id,
        color: colorForKey(combo.name || combo.rule_id || combo.id || '组合'),
        regions: [region],
      }]
    })
  })
})
</script>

<template>
  <section class="panel result-tabs workbench-preview-tabs">
    <div class="panel-title panel-title--tight">
      <b>识别结果</b>
    </div>

    <div class="tab-bar tab-bar--dense" role="tablist">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="tab-button"
        :class="{ active: activeTab === tab.key }"
        type="button"
        role="tab"
        @click="switchTab(tab.key)"
      >
        {{ tab.label }}<template v-if="'count' in tab"> ({{ tab.count }})</template>
      </button>
    </div>

    <div class="tab-content tab-content--canvas">
      <div v-if="activeTab === 'component-identification'" class="component-identification-split">
        <div class="preview-box preview-box--hero component-identification-preview">
          <DrawingPreview :pages="previewPages" :components="components" />
        </div>

        <section class="component-identification-side">
          <div class="component-identification-title">
            <b>元件标识列表</b>
            <span class="label">components</span>
          </div>

          <div class="component-identification-list" role="list" aria-label="元件标识列表">
            <div
              v-if="loading && !components.length"
              class="recognition-loading-panel recognition-loading-panel--wide"
              role="status"
              aria-live="polite"
            >
              <div class="recognition-loader" aria-hidden="true">
                <span></span>
                <span></span>
                <span></span>
              </div>
              <h3>识别中</h3>
              <p>正在定位图纸区域与元件候选，请稍候。</p>
              <div class="recognition-skeleton-grid" aria-hidden="true">
                <span></span>
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>

            <div class="empty-editor" v-else-if="!components.length">
              <h3>无元件数据</h3>
              <p>识别结果中暂未检测到元件。</p>
            </div>

            <article
              v-for="(comp, index) in components"
              v-else
              :key="`${comp.reference_id || comp.id || ''}-${designation(comp)}-${comp.page}-${index}`"
              class="result-card component-result-card"
              role="listitem"
            >
              <div class="component-result-head">
                <span class="component-color-dot" :style="{ background: colorOf(comp) }"></span>
                <strong>{{ comp.label || designation(comp) }}</strong>
              </div>
              <dl class="component-result-meta">
                <div><dt>元件代号</dt><dd>{{ designation(comp) }}</dd></div>
                <div><dt>类型</dt><dd>{{ comp.component_type || '未分类' }}</dd></div>
                <div><dt>页码</dt><dd>第 {{ comp.page }} 页</dd></div>
                <div v-if="comp.occurrence_count"><dt>数量</dt><dd>{{ comp.occurrence_count }}</dd></div>
                <div v-if="confidencePercent(comp)"><dt>置信度</dt><dd>{{ confidencePercent(comp) }}</dd></div>
              </dl>
            </article>
          </div>
        </section>
      </div>

      <div v-if="activeTab === 'combinations'" class="component-identification-split">
        <div class="preview-box preview-box--hero component-identification-preview">
          <DrawingPreview :pages="previewPages" :components="components" :annotations="combinationAnnotations" />
        </div>

        <section class="component-identification-side">
          <div class="component-identification-title">
            <b>组合规则信息</b>
            <span class="label">combinations</span>
          </div>

          <div class="component-identification-list" role="list" aria-label="组合规则信息">
            <div class="empty-editor" v-if="!combinations.length">
              <h3>无组合数据</h3>
              <p>识别结果中暂未检测到组合。</p>
            </div>
            <div v-for="combo in combinations" :key="combo.id" v-else class="result-card component-result-card" role="listitem">
              <div class="component-result-head">
                <strong>{{ combo.name || combo.rule_id }}</strong>
              </div>
              <dl class="component-result-meta">
                <div>
                  <dt>规则来源</dt>
                  <dd>{{ combo.rule_layer === 'custom' ? '自定义' : '内置' }}</dd>
                </div>
                <div>
                  <dt>页码</dt>
                  <dd>第 {{ combo.page }} 页</dd>
                </div>
                <div>
                  <dt>成员数</dt>
                  <dd>{{ combo.members?.length || 0 }}</dd>
                </div>
                <div v-if="combo.rule_id">
                  <dt>规则 ID</dt>
                  <dd>{{ combo.rule_id }}</dd>
                </div>
                <div v-if="combo.evidence">
                  <dt>组合依据</dt>
                  <dd>{{ combo.evidence }}</dd>
                </div>
                <div v-if="combo.members?.length">
                  <dt>成员明细</dt>
                  <dd>{{ combo.members.map((member, index) => combinationMemberLabel(member, index)).join(' / ') }}</dd>
                </div>
              </dl>
            </div>
          </div>
        </section>
      </div>

      <div v-if="activeTab === 'tag-table'" class="result-card">
        <div class="panel-title panel-title--tight">
          <b>图纸标签表</b>
          <span class="label">component_table</span>
        </div>
        <div class="badge-row" style="margin-top: 10px">
          <button class="button" type="button" @click="copyJson(componentTable)">复制 JSON</button>
          <button class="button" type="button" @click="rawExpanded['tag-table'] = !rawExpanded['tag-table']">
            {{ rawExpanded['tag-table'] ? '收起原始 JSON' : '展开原始 JSON' }}
          </button>
        </div>

        <div v-if="isEmptyPayload(componentTable)" class="empty-editor" style="margin-top: 10px">
          <h3>暂无图纸标签表</h3>
          <p>后端未返回 component_table 或字段为空，不影响元件/预览查看。</p>
        </div>

        <template v-else>
          <div v-if="normalizeRows(componentTable)" class="component-table-wrap" style="margin-top: 10px">
            <table class="component-table">
              <thead>
                <tr>
                  <th v-for="col in tableColumns(normalizeRows(componentTable) || [])" :key="col">{{ col }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, index) in (normalizeRows(componentTable) || [])" :key="index">
                  <td v-for="col in tableColumns(normalizeRows(componentTable) || [])" :key="`${index}-${col}`" class="mono">
                    {{ typeof row[col] === 'string' || typeof row[col] === 'number' ? row[col] : row[col] == null ? '--' : JSON.stringify(row[col]) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div v-else class="title-block-table" style="margin-top: 10px">
            <table class="component-table title-block-fields configuration-table">
              <tbody>
                <tr v-for="[key, value] in kvEntries(componentTable)" :key="key">
                  <th class="mono">{{ key }}</th>
                  <td class="mono">{{ typeof value === 'string' || typeof value === 'number' ? value : value == null ? '--' : JSON.stringify(value) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>

        <pre v-if="rawExpanded['tag-table']" style="margin-top: 10px">{{ toPrettyJson(componentTable) }}</pre>
      </div>

      <div v-if="activeTab === 'control-signal'" class="result-card">
        <div class="panel-title panel-title--tight">
          <b>控制/信号信息</b>
          <span class="label">control_signal_configuration</span>
        </div>
        <div class="badge-row" style="margin-top: 10px">
          <button class="button" type="button" @click="copyJson(controlSignalConfiguration)">复制 JSON</button>
          <button class="button" type="button" @click="rawExpanded['control-signal'] = !rawExpanded['control-signal']">
            {{ rawExpanded['control-signal'] ? '收起原始 JSON' : '展开原始 JSON' }}
          </button>
        </div>

        <div v-if="isEmptyPayload(controlSignalConfiguration)" class="empty-editor" style="margin-top: 10px">
          <h3>暂无控制/信号信息</h3>
          <p>后端未返回 control_signal_configuration 或字段为空，不影响元件/预览查看。</p>
        </div>

        <template v-else>
          <div v-if="controlSignals.length || controlControls.length" class="preview-grid" style="margin-top: 10px">
            <div class="component-table-wrap">
              <table class="component-table">
                <thead>
                  <tr>
                    <th>signals</th>
                    <th>value</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(item, index) in controlSignals" :key="`signal-${index}`">
                    <td class="mono">{{ item?.name || item?.id || `signal-${index + 1}` }}</td>
                    <td class="mono">{{ typeof item === 'string' || typeof item === 'number' ? item : JSON.stringify(item) }}</td>
                  </tr>
                  <tr v-if="!controlSignals.length">
                    <td colspan="2" class="mono">--</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="component-table-wrap">
              <table class="component-table">
                <thead>
                  <tr>
                    <th>controls</th>
                    <th>value</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(item, index) in controlControls" :key="`control-${index}`">
                    <td class="mono">{{ item?.name || item?.id || `control-${index + 1}` }}</td>
                    <td class="mono">{{ typeof item === 'string' || typeof item === 'number' ? item : JSON.stringify(item) }}</td>
                  </tr>
                  <tr v-if="!controlControls.length">
                    <td colspan="2" class="mono">--</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div v-else class="title-block-table" style="margin-top: 10px">
            <table class="component-table title-block-fields configuration-table">
              <tbody>
                <tr v-for="[key, value] in kvEntries(controlSignalConfiguration)" :key="key">
                  <th class="mono">{{ key }}</th>
                  <td class="mono">{{ typeof value === 'string' || typeof value === 'number' ? value : value == null ? '--' : JSON.stringify(value) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>

        <pre v-if="rawExpanded['control-signal']" style="margin-top: 10px">{{ toPrettyJson(controlSignalConfiguration) }}</pre>
      </div>

      <div v-if="activeTab === 'title-block'" class="result-card">
        <div class="panel-title panel-title--tight">
          <b>图签信息</b>
          <span class="label">title_block</span>
        </div>
        <div class="badge-row" style="margin-top: 10px">
          <button class="button" type="button" @click="copyJson(titleBlock)">复制 JSON</button>
          <button class="button" type="button" @click="rawExpanded['title-block'] = !rawExpanded['title-block']">
            {{ rawExpanded['title-block'] ? '收起原始 JSON' : '展开原始 JSON' }}
          </button>
        </div>

        <div v-if="isEmptyPayload(titleBlock)" class="empty-editor" style="margin-top: 10px">
          <h3>未解析到图签信息</h3>
          <p>后端未返回 title_block 或字段为空，不影响元件/预览查看。</p>
        </div>

        <div v-else class="title-block-table" style="margin-top: 10px">
          <table class="component-table title-block-fields configuration-table">
            <tbody>
              <tr v-for="[key, value] in titleBlockEntries(titleBlock)" :key="key">
                <th class="mono">{{ key }}</th>
                <td class="mono">{{ typeof value === 'string' || typeof value === 'number' ? value : value == null ? '--' : JSON.stringify(value) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <pre v-if="rawExpanded['title-block']" style="margin-top: 10px">{{ toPrettyJson(titleBlock) }}</pre>
      </div>
    </div>
  </section>
</template>
