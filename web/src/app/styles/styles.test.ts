import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('styles theme tokens', () => {
  it('defines the accent color token used by primary buttons', () => {
    const css = readFileSync(resolve(process.cwd(), 'src/app/styles/styles.css'), 'utf8')

    expect(css).toMatch(/--accent\s*:/)
  })

  it('uses non-danger color for info messages', () => {
    const css = readFileSync(resolve(process.cwd(), 'src/app/styles/styles.css'), 'utf8')

    const baseMessageBlock = /\.message\s*\{[\s\S]*?\}/.exec(css)?.[0] ?? ''
    expect(baseMessageBlock).not.toContain('var(--red)')
    expect(css).toMatch(/\.message\.error\s*\{[\s\S]*var\(--red\)/)
  })

  it('keeps workbench result tables on dark surfaces', () => {
    const css = readFileSync(resolve(process.cwd(), 'src/app/styles/diff.css'), 'utf8')

    expect(css).toMatch(/\.diff-a-root\s+\.workbench-preview-tabs\s+\.component-table-wrap[\s\S]*background:\s*rgba\(/)
    expect(css).toMatch(/\.diff-a-root\s+\.workbench-preview-tabs\s+\.title-block-table[\s\S]*background:\s*rgba\(/)
    expect(css).toMatch(/\.diff-a-root\s+\.workbench-preview-tabs\s+\.component-table\s+th[\s\S]*background:\s*rgba\(/)
  })
})
