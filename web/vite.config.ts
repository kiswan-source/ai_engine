/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      // Backend (FastAPI, api/main.py) runs on :8001 in dev (see CLAUDE.md).
      // Frontend talks only to these prefixes (FRONTEND_ARCHITECTURE.md §6:
      // apiClient.ts is the sole HTTP exit point) — proxy keeps it same-origin
      // in dev so no CORS/base-URL branching is needed between dev and prod.
      '/api': 'http://localhost:8001',
      '/health': 'http://localhost:8001',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
  },
})
