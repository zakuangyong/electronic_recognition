// @vitest-environment node
import { describe, expect, it } from 'vitest'

import { backendDevServer, devProxy } from './dev-proxy'

describe('vite dev proxy', () => {
  it('proxies api requests to backend server', () => {
    expect(devProxy['/api']).toMatchObject({
      target: backendDevServer,
      changeOrigin: true,
    })
  })

  it('proxies analyze uploads to backend server', () => {
    expect(devProxy['/analyze']).toMatchObject({
      target: backendDevServer,
      changeOrigin: true,
    })
  })
})
