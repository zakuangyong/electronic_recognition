import { defineStore } from 'pinia'

import { appRoutePaths } from '../routes'

export const useAppStore = defineStore('app', {
  state: () => ({
    title: 'Electronic Recognition',
    primaryRoute: '/workbench',
    routes: [...appRoutePaths] as string[],
  }),
})
