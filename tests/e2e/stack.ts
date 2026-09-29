/**
 * Global setup: starts scripts/dev-stack.mjs over an IPC channel, waits for its `ready` message
 * and returns the teardown, which asks the stack to stop so the embedded PostgreSQL is shut down
 * and its directory deleted rather than orphaned.
 */
import { fork } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { API_PORT, STUDIO_PORT } from './playwright.config';

const here = dirname(fileURLToPath(import.meta.url));
const script = resolve(here, '../../scripts/dev-stack.mjs');

export default async function globalSetup(): Promise<() => Promise<void>> {
  const stack = fork(script, [], {
    cwd: resolve(here, '../..'),
    // The suite checks the example companies, so it always seeds the fixture.
    env: {
      ...process.env,
      ONTAIX_API_PORT: String(API_PORT),
      ONTAIX_STUDIO_PORT: String(STUDIO_PORT),
      ONTAIX_SEED: 'fixture',
      ONTAIX_PGDATA: 'ephemeral',
    },
    stdio: ['ignore', 'inherit', 'inherit', 'ipc'],
  });
  const exited = new Promise<void>((ok) => stack.once('exit', () => ok()));
  const stop = async () => {
    if (stack.exitCode === null && stack.connected) stack.send('stop');
    await exited;
  };
  const ready = new Promise<void>((ok, fail) => {
    const timer = setTimeout(() => fail(new Error('the local stack did not become ready within 180 s')), 180_000);
    stack.on('message', (m) => {
      if (m === 'ready') {
        clearTimeout(timer);
        ok();
      }
    });
    stack.once('exit', (code) => {
      clearTimeout(timer);
      fail(new Error(`the local stack exited with code ${code} before it was ready`));
    });
  });
  try {
    await ready;
  } catch (err) {
    await stop();
    throw err;
  }
  return stop;
}
