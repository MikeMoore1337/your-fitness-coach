import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import type { UserConfig } from 'vite';

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

export default defineConfig({
  plugins: [react()],
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
      '/api': 'http://127.0.0.1:8000',
      '/static/exercise-guides': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './tests/setup.ts',
    include: ['tests/unit/**/*.test.{ts,tsx}'],
    css: true,
    ...(testReporters ? { reporters: testReporters } : {}),
  },
});
