import { createMemoryHistory } from 'vue-router'
import { describe, expect, it } from 'vitest'

import { appRoutePaths } from './routes'
import { createAppRouter } from './router'

describe('app router', () => {
  it('redirects root navigation to workbench', async () => {
    const router = createAppRouter(createMemoryHistory())

    await router.push('/')
    await router.isReady()

    expect(router.currentRoute.value.fullPath).toBe('/workbench')
  })

  it('exposes root redirect and shared app routes', () => {
    const router = createAppRouter(createMemoryHistory())
    const paths = router.getRoutes().map((route) => route.path)

    expect(paths).toContain('/')
    expect(paths).toEqual(expect.arrayContaining(appRoutePaths))
    expect(paths).toContain('/drawing-diff')
  })
})
