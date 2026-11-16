import { defineConfig } from '@playwright/test';
import crossBrowser from './playwright.cross-browser.config';

export default defineConfig(crossBrowser, {
  testMatch: '**/v13-950-baseline.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
});
