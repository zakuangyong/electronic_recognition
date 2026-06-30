import type { ComponentData } from '../types/results'

// A fixed, high-contrast palette. Colors are assigned deterministically per
// component group key so the same component type always renders in the same
// color across the preview overlay and the legend.
const PALETTE = [
  '#ef4444',
  '#f97316',
  '#f59e0b',
  '#16a34a',
  '#10b981',
  '#06b6d4',
  '#3b82f6',
  '#6366f1',
  '#8b5cf6',
  '#d946ef',
  '#ec4899',
  '#0ea5e9',
  '#65a30d',
  '#dc2626',
  '#9333ea',
]

/** The key used to group/color a component: prefer its type, fall back to label. */
export function componentColorKey(component: Pick<ComponentData, 'component_type' | 'label'>): string {
  return (component.component_type || component.label || '未分类').trim() || '未分类'
}

export function colorForKey(key: string): string {
  let hash = 0
  for (let index = 0; index < key.length; index += 1) {
    hash = (hash * 31 + key.charCodeAt(index)) >>> 0
  }
  return PALETTE[hash % PALETTE.length]
}

export interface LegendEntry {
  key: string
  color: string
  count: number
}

/** Distinct component groups present in the list, each with its color and count. */
export function buildLegend(components: ComponentData[]): LegendEntry[] {
  const groups = new Map<string, number>()
  for (const component of components) {
    const key = componentColorKey(component)
    groups.set(key, (groups.get(key) || 0) + 1)
  }
  return Array.from(groups.entries())
    .map(([key, count]) => ({ key, color: colorForKey(key), count }))
    .sort((a, b) => b.count - a.count)
}
