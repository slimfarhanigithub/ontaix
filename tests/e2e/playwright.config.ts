import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import { defineConfig } from '../../apps/studio/test-support/playwright';

const here = dirname(fileURLToPath(import.meta.url));

/** Ports of the stack the run boots; distinct from the dev defaults so a running dev stack is left alone. */
export const API_PORT = 8788;
export const STUDIO_PORT = 5788;

export default defineConfig({
  testDir: here,
  outputDir: resolve(here, 'output/test-results'),
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 120_000,
  reporter: [['list']],
  // Boots scripts/dev-stack.mjs (embedded PostgreSQL, seed, API, Vite) and stops it afterwards.
  globalSetup: resolve(here, 'stack.ts'),
  use: {
    browserName: 'chromium',
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    baseURL: `http://localhost:${STUDIO_PORT}`,
  },
});
