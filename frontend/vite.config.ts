import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// base './' keeps asset URLs working behind Ingress path rewrite (/app → /).
export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
