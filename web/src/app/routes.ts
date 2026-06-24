import type { RouteRecordRaw } from 'vue-router'

export const appRouteRecords: RouteRecordRaw[] = [
  { path: '/workbench', component: () => import('../views/WorkbenchView.vue') },
  { path: '/results/:resultId', component: () => import('../views/ResultView.vue') },
  { path: '/knowledge', component: () => import('../views/KnowledgeView.vue') },
  { path: '/search', component: () => import('../views/SearchView.vue') },
]

export const appRoutePaths = appRouteRecords.map((route) => route.path)
