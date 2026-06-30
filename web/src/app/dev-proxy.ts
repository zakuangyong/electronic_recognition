export const backendDevServer = 'http://127.0.0.1:8892'

export const devProxy = {
  '/api': {
    target: backendDevServer,
    changeOrigin: true,
  },
  '/analyze': {
    target: backendDevServer,
    changeOrigin: true,
  },
} as const
