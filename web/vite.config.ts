import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { devProxy } from './src/app/dev-proxy'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: devProxy,
  },
})
