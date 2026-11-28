import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { agentationDevelopmentPlugin } from './devtools/agentation-dev-plugin';
import type { Plugin, UserConfig } from 'vite';

type TestReporters = NonNullable<NonNullable<UserConfig['test']>['reporters']>;

const testReporters: TestReporters | undefined = process.env.ALLURE_RESULTS_DIR
  ? [
      'default',
      [
        process.env.ALLURE_VITEST_REPORTER_PATH ?? 'allure-vitest/reporter',
        { resultsDir: process.env.ALLURE_RESULTS_DIR },
      ],
    ]
  : undefined;
const apiPort = process.env.PW_API_PORT ?? '8000';

function preloadHtmlEntry(): Plugin {
  let base = '/';
  return {
    name: 'yfc-preload-html-entry',
    apply: 'build',
    configResolved(config) {
      base = config.base;
    },
    transformIndexHtml: {
      order: 'post',
      handler(_html, context) {
        const entry = Object.values(context.bundle ?? {}).find(
          (item) =>
            item.type === 'chunk' && item.isEntry && item.facadeModuleId === context.filename,
        );
        if (!entry) return [];
        // Later dynamic imports can otherwise preload the already executed entry a second time.
        return [
          {
            tag: 'link',
            attrs: { rel: 'modulepreload', crossorigin: '', href: `${base}${entry.fileName}` },
            injectTo: 'head-prepend',
          },
        ];
      },
    },
  };
}

export default defineConfig({
  plugins: [react(), agentationDevelopmentPlugin(), preloadHtmlEntry()],
  cacheDir: '../.artifacts/runtime/cache/vite',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // Source maps are not consumed by an error tracker and should not be shipped publicly.
    sourcemap: false,
    manifest: true,
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': `http://127.0.0.1:${apiPort}`,
      '/static/exercise-guides': `http://127.0.0.1:${apiPort}`,
      '/health': `http://127.0.0.1:${apiPort}`,
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './tests/setup.ts',
    include: ['tests/unit/**/*.test.{ts,tsx}'],
    css: true,
    ...(testReporters
      ? {
          reporters: testReporters,
          // Resolve the adapter against the active Vitest runner, not its isolated peer.
          server: { deps: { inline: [/allure-vitest/] } },
        }
      : {}),
  },
});
