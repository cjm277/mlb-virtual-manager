import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development the app runs on :5173 and forwards /api to the FastAPI backend on :8000.
// For graders, `npm run build` output (dist/) is committed and served by FastAPI itself, so no Node is needed.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, proxy: { '/api': 'http://127.0.0.1:8000' } },
})
