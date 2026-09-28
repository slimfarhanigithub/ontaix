import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import { defineConfig } from '../../apps/studio/test-support/playwright';

const here = dirname(fileURLToPath(import.meta.url));
const studio = resolve(here, '../../apps/studio');

/** Port the built Studio is served on for the run. */
export const STUDIO_PORT = 4787;

export default defineConfig({
  testDir: here,
  outputDir: resolve(here, 'output/test-results'),
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 180_000,
  reporter: [['list'], ['html', { outputFolder: resolve(here, 'output/report'), open: 'never' }]],
  use: {
    browserName: 'chromium',
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    baseURL: `http://127.0.0.1:${STUDIO_PORT}`,
  },
  webServer: {
    command: 'pnpm exec vite build && pnpm exec vite preview --port 4787 --strictPort --host 127.0.0.1',
    cwd: studio,
    // Test hooks (seeded random source, in-browser mock API) are compiled in only for this build.
    env: { VITE_ONTAIX_TEST_HOOKS: 'true' },
    url: `http://127.0.0.1:${STUDIO_PORT}/`,
    reuseExistingServer: false,
    timeout: 180_000,
  },
});
