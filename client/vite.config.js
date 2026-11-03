import react from '@vitejs/plugin-react'
import basicSsl from '@vitejs/plugin-basic-ssl'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // API_URL / PORT come from client/.env(.local) or the shell, so a second copy
  // of the app can run beside another one without editing this file.
  const env = { ...loadEnv(mode, process.cwd(), ''), ...process.env }
  // HTTPS=1 (start_aura_demo.bat): a self-signed https server reachable on the Wi-Fi, because phones only
  // allow the camera on https pages — that is what lets a phone scan the demo kiosk QR
  const https = env.HTTPS === '1'

  return {
    plugins: [react(), ...(https ? [basicSsl()] : [])],
    server: {
      port: Number(env.PORT) || 5173,
      strictPort: true,
      host: https ? true : undefined,
      proxy: {
        '/api': env.API_URL || 'http://localhost:4000',
      },
    },
  }
})
