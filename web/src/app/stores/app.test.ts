import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { appRoutePaths } from '../routes'
import { useAppStore } from './app'

describe('app store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('creates a store with app shell metadata', () => {
    const store = useAppStore()

    expect(store.title).toBe('Electronic Recognition')
    expect(store.primaryRoute).toBe('/workbench')
    expect(store.routes).toEqual(appRoutePaths)
  })
})
