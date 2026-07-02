import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      // Local non-Docker dev: `dotnet run` launches the backend on
      // http://localhost:8080 (see backend/Properties/launchSettings.json), so
      // this makes the browser see everything as same-origin here too, just
      // like the nginx reverse proxy does in the Docker/production path -- no
      // CORS configuration needed in either case.
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
})
