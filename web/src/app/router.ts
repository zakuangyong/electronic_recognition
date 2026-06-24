import {
  createMemoryHistory,
  createRouter,
  createWebHistory,
  type RouterHistory,
} from 'vue-router'

import { appRouteRecords } from './routes'

function createHistory(): RouterHistory {
  return typeof window === 'undefined' ? createMemoryHistory() : createWebHistory()
}

export function createAppRouter(history: RouterHistory = createHistory()) {
  return createRouter({
    history,
    routes: [
      { path: '/', redirect: '/workbench' },
      ...appRouteRecords,
    ],
  })
}
