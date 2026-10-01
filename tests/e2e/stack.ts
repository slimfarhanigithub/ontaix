/**
 * Global setup: starts scripts/dev-stack.mjs over an IPC channel, waits for its `ready` message
 * and returns the teardown, which asks the stack to stop so the embedded PostgreSQL is shut down
 * and its directory deleted rather than orphaned.
 *
 * The Studio runs without a default dev identity, so a page opened without `?user=` shows the
 * sign-in page. Once the stack is ready, a super admin is created in its database with a password
 * generated for this run (fixtures/bootstrap_super_admin.py, as `python -m app.admin` does); the
 * specs read both from E2E_SUPER_ADMIN_EMAIL and E2E_SUPER_ADMIN_PASSWORD. Nothing is written to
 * disk or printed.
 */
import { fork, spawnSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { API_PORT, STUDIO_PORT } from './playwright.config';

const here = dirname(fileURLToPath(import.meta.url));
const script = resolve(here, '../../scripts/dev-stack.mjs');
const apiDir = resolve(here, '../../apps/api');
const bootstrap = resolve(here, 'fixtures/bootstrap_super_admin.py');

function createSuperAdmin(databaseUrl: string): void {
  const email = `e2e-root-${randomBytes(4).toString('hex')}@platform.test`;
  const password = randomBytes(18).toString('base64url');
  const python =
    process.platform === 'win32' ? join(apiDir, '.venv', 'Scripts', 'python.exe') : join(apiDir, '.venv', 'bin', 'python');
  const run = spawnSync(python, [bootstrap], {
    cwd: apiDir,
    env: { ...process.env, ONTAIX_DATABASE_URL: databaseUrl, ONTAIX_ENVIRONMENT: 'dev' },
    input: JSON.stringify({ email, password }),
    encoding: 'utf8',
  });
  if (run.status !== 0) throw new Error(`creating the e2e super admin failed: ${run.stderr}`);
  process.env.E2E_SUPER_ADMIN_EMAIL = email;
  process.env.E2E_SUPER_ADMIN_PASSWORD = password;
}

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
      VITE_ONTAIX_DEV_USER: '',
    },
    stdio: ['ignore', 'inherit', 'inherit', 'ipc'],
  });
  const exited = new Promise<void>((ok) => stack.once('exit', () => ok()));
  const stop = async () => {
    if (stack.exitCode === null && stack.connected) stack.send('stop');
    await exited;
  };
  let databaseUrl: string | null = null;
  stack.on('message', (m) => {
    if (typeof m === 'object' && m !== null && (m as { type?: string }).type === 'database') {
      databaseUrl = (m as { url: string }).url;
    }
  });
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
    if (!databaseUrl) throw new Error('the local stack did not report its database');
    createSuperAdmin(databaseUrl);
  } catch (err) {
    await stop();
    throw err;
  }
  return stop;
}
