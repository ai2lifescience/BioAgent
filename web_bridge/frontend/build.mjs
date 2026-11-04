// Build the host SDK from the same TypeScript used by the local demo.
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../../', import.meta.url));
const require = createRequire(path.join(root, 'frontend/package.json'));
const { build } = await import(pathToFileURL(require.resolve('vite')).href);
await build({
  configFile: false,
  build: {
    outDir: path.join(root, 'frontend/dist/static'),
    emptyOutDir: false,
    lib: { entry: path.join(root, 'web_bridge/frontend/embed.ts'), name: 'BioAgentEmbed', formats: ['iife'], fileName: () => 'assistant-embed.js' },
    minify: false,
  },
});
