import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: '/',
  // Keep `npm run dev` connected to the stdlib API server. The static
  // production build is still served by interfaces.web, while local Vite
  // development forwards API/SSE requests without CORS workarounds.
  server: {
    proxy: Object.fromEntries([
      '/config', '/health', '/sessions', '/workspace', '/run_stream',
      '/approve_stream', '/runs', '/knowledge', '/website', '/static',
    ].map(path => [path, { target: process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000', changeOrigin: false }])),
  },
  build: {
    // `dist` is disposable build output. The Python server serves it, while
    // persistent sessions and job state stay in the repository-level runtime/.
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: 'index.html',
        assistant: 'assistant.html',
        assistantDemo: 'assistant-demo.html',
      },
      output: {
        entryFileNames: 'static/[name]-[hash].js',
        chunkFileNames: 'static/[name]-[hash].js',
        assetFileNames: (assetInfo) => {
          return 'static/[name]-[hash][extname]';
        },
      },
    },
  },
});
