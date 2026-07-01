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

  it('defines adapted correction comparison layout styles', () => {
    const css = readFileSync(resolve(process.cwd(), 'src/app/styles/styles.css'), 'utf8')

    expect(css).toMatch(/\.drawing-correction-split\s*\{[\s\S]*grid-template-columns:\s*minmax\(0,\s*1\.18fr\)\s+minmax\(420px,\s*0\.82fr\)/)
    expect(css).toMatch(/\.drawing-correction-list\s*\{[\s\S]*overflow-y:\s*auto/)
    expect(css).toMatch(/\.drawing-correction-list\s+\.component-table-wrap\s*\{[\s\S]*overflow-x:\s*auto/)
  })

  it('keeps correction comparison tables on dark surfaces', () => {
    const css = readFileSync(resolve(process.cwd(), 'src/app/styles/diff.css'), 'utf8')

    expect(css).toMatch(/\.diff-a-root\s+\.drawing-correction-list\s+\.label-compare-card[\s\S]*background:\s*rgba\(/)
    expect(css).toMatch(/\.diff-a-root\s+\.drawing-correction-list\s+\.component-table-wrap[\s\S]*background:\s*rgba\(/)
    expect(css).toMatch(/\.diff-a-root\s+\.drawing-correction-list\s+\.component-table\s+th[\s\S]*background:\s*rgba\(/)
  })
})
