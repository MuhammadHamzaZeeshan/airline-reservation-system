import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev: `npm run dev` proxies the API to the Nginx edge on :8080. Prod: Nginx serves dist/ and proxies /v1 itself.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { '/v1': 'http://localhost:8080', '/health': 'http://localhost:8080' } },
})
