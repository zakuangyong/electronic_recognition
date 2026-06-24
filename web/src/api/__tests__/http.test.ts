import { describe, expect, it } from 'vitest'

import { buildApiUrl, normalizeError } from '../http'

describe('http helpers', () => {
  it('builds absolute api url from explicit base url', () => {
    expect(buildApiUrl('/api/config', 'http://localhost:8892')).toBe(
      'http://localhost:8892/api/config',
    )
  })

  it('keeps relative path when base url is empty', () => {
    expect(buildApiUrl('/api/config', '')).toBe('/api/config')
  })

  it('normalizes backend detail payload', () => {
    expect(normalizeError({ detail: 'boom' }, 'fallback')).toBe('boom')
  })

  it('normalizes nested backend detail message', () => {
    expect(normalizeError({ detail: { message: 'nested boom' } }, 'fallback')).toBe(
      'nested boom',
    )
  })

  it('normalizes top-level message payload', () => {
    expect(normalizeError({ message: 'top level boom' }, 'fallback')).toBe(
      'top level boom',
    )
  })

  it('falls back when payload detail is unavailable', () => {
    expect(normalizeError({ detail: { code: 'boom' } }, 'fallback')).toBe(
      'fallback',
    )
  })
})
