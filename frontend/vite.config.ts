import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, proxy: { '/api': { target: process.env.BUS_API_TARGET ?? 'http://127.0.0.1:8000', changeOrigin: true } } },
  test: { environment: 'jsdom', restoreMocks: true, clearMocks: true },
});
