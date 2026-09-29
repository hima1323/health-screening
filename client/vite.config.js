import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // API_URL / PORT come from client/.env(.local) or the shell, so a second copy
  // of the app can run beside another one without editing this file.
  const env = { ...loadEnv(mode, process.cwd(), ''), ...process.env }

  return {
    plugins: [react()],
    server: {
      port: Number(env.PORT) || 5173,
      strictPort: true,
      proxy: {
        '/api': env.API_URL || 'http://localhost:4000',
      },
    },
  }
})
