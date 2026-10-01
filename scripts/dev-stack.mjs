#!/usr/bin/env node
/**
 * Local stack without Docker: an embedded PostgreSQL 16 (the api's `pgserver` dev dependency),
 * the seeded demo tenant, the API under uvicorn and the Studio's Vite dev server wired to it.
 *
 *   pnpm dev:stack                   # Studio http://localhost:5173, API http://127.0.0.1:8000
 *
 * Environment:
 *   ONTAIX_API_PORT        API port (default 8000)
 *   ONTAIX_STUDIO_PORT     Studio port (default 5173)
 *   ONTAIX_DATABASE_URL    use this PostgreSQL instead of the embedded one (CI: postgres:16 service)
 *   ONTAIX_SEED            empty (default here: the demo tenant and its users, no company) or
 *                          fixture (the Northwind and Aurora example)
 *   VITE_ONTAIX_DEV_USER   dev identity the Studio sends as X-Ontaix-User (default: the seed's
 *                          full-access demo user demo@northwind.com); set it empty to see the
 *                          sign-in page, which needs an account (python -m app.admin, see below)
 *   ONTAIX_DEV_IDENTITY_HEADER  whether the API accepts X-Ontaix-User (default here: true). The API
 *                          accepts the header only in dev or test with this flag on; it is off by
 *                          default everywhere else, and the API refuses to start with it on outside
 *                          dev and test
 *   ONTAIX_PGDATA          folder of the embedded database (default: %LOCALAPPDATA%\Ontaix\pgdata on
 *                          Windows, ~/.local/share/ontaix/pgdata elsewhere); `ephemeral` uses a
 *                          temporary folder deleted on exit, as the end-to-end tests do
 *
 *   pnpm dev:stack -- --reset        # delete the embedded database first, then seed afresh
 *
 * Sign-in: the stack runs the API with ONTAIX_DEV_IDENTITY_HEADER=true and allows the Studio's
 * origins (http://localhost:<port> and http://127.0.0.1:<port>) for the session cookie's CSRF check.
 * The seed creates no account. To sign in with a password, create the super admin once from
 * apps/api with the stack's database in ONTAIX_DATABASE_URL:
 *   .venv/Scripts/python -m app.admin create-super-admin <email>   (prompts twice, no echo)
 * then create organizations and accounts from the platform portal.
 *
 * When started by another Node process with an IPC channel, the stack also sends
 * { type: 'database', url } once the database is migrated and seeded, so end-to-end tests can
 * bootstrap an account in it.
 *
 * The embedded database keeps its data between runs; the seed never changes an existing tenant,
 * so ONTAIX_SEED only matters for a new or reset database. The stack stops on Ctrl+C, SIGTERM, or, when started by another Node
 * process with an IPC channel, on the message `stop` or when that parent goes away.
 */
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, rmSync } from 'node:fs';
import { homedir } from 'node:os';
import { createConnection } from 'node:net';
import { dirname, join, resolve } from 'node:path';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const apiDir = join(root, 'apps', 'api');
const studioDir = join(root, 'apps', 'studio');
const isWindows = process.platform === 'win32';

const apiPort = Number(process.env.ONTAIX_API_PORT || 8000);
const studioPort = Number(process.env.ONTAIX_STUDIO_PORT || 5173);
const apiUrl = `http://127.0.0.1:${apiPort}`;
const studioUrl = `http://127.0.0.1:${studioPort}`;

/**
 * Holds pgserver open until stdin closes, then stops the server. Its folder is argv[1], or a
 * temporary folder deleted on exit when argv[1] is `ephemeral`.
 */
const EMBEDDED_POSTGRES = `
import pathlib, sys, tempfile
import pgserver
if sys.argv[1] == "ephemeral":
    pgdata = pathlib.Path(tempfile.mkdtemp(prefix="ontaix-dev-pg-")) / "pgdata"
    server = pgserver.get_server(pgdata, cleanup_mode="delete")
else:
    pgdata = pathlib.Path(sys.argv[1])
    pgdata.parent.mkdir(parents=True, exist_ok=True)
    server = pgserver.get_server(pgdata, cleanup_mode="stop")
print(server.get_uri(), flush=True)
try:
    sys.stdin.read()
except KeyboardInterrupt:
    pass
finally:
    server.cleanup()
`;

const pgdata =
  process.env.ONTAIX_PGDATA ||
  (isWindows
    ? join(process.env.LOCALAPPDATA || join(homedir(), 'AppData', 'Local'), 'Ontaix', 'pgdata')
    : join(homedir(), '.local', 'share', 'ontaix', 'pgdata'));
const reset = process.argv.includes('--reset');

const children = [];
let postgres = null;
let stopping = false;

function log(line) {
  process.stdout.write(`[dev-stack] ${line}\n`);
}

function python() {
  const venvPython = isWindows ? join(apiDir, '.venv', 'Scripts', 'python.exe') : join(apiDir, '.venv', 'bin', 'python');
  if (!existsSync(venvPython)) {
    log('apps/api/.venv is missing, running uv sync');
    const sync = spawnSync('uv', ['sync', '--frozen'], { cwd: apiDir, stdio: 'inherit', shell: isWindows });
    if (sync.status !== 0) throw new Error('uv sync failed');
  }
  return venvPython;
}

function prefixed(child, name) {
  for (const stream of [child.stdout, child.stderr]) {
    if (!stream) continue;
    createInterface({ input: stream }).on('line', (line) => process.stdout.write(`[${name}] ${line}\n`));
  }
}

function start(name, command, args, options) {
  const child = spawn(command, args, { stdio: ['ignore', 'pipe', 'pipe'], ...options });
  prefixed(child, name);
  child.on('exit', (code) => {
    if (!stopping) {
      log(`${name} exited with code ${code}; stopping the stack`);
      void stop(1);
    }
  });
  children.push(child);
  return child;
}

async function startPostgres(py) {
  if (pgdata !== 'ephemeral' && reset && existsSync(pgdata)) {
    log(`--reset: deleting ${pgdata}`);
    rmSync(pgdata, { recursive: true, force: true });
  }
  if (pgdata !== 'ephemeral') log(`embedded PostgreSQL data in ${pgdata}`);
  const child = spawn(py, ['-c', EMBEDDED_POSTGRES, pgdata], { cwd: apiDir, stdio: ['pipe', 'pipe', 'pipe'] });
  postgres = child;
  createInterface({ input: child.stderr }).on('line', (line) => process.stdout.write(`[postgres] ${line}\n`));
  const uri = await new Promise((ok, fail) => {
    const lines = createInterface({ input: child.stdout });
    lines.once('line', ok);
    child.once('exit', (code) => fail(new Error(`embedded PostgreSQL exited with code ${code}`)));
  });
  log(`embedded PostgreSQL at ${uri.replace(/\/\/[^@]*@/, '//')}`);
  return uri;
}

function seed(py, env) {
  log(`migrating and seeding the demo tenant (${env.ONTAIX_SEED})`);
  const run = spawnSync(py, ['-m', 'app.seed'], { cwd: apiDir, env, stdio: 'inherit' });
  if (run.status !== 0) throw new Error('python -m app.seed failed');
}

/** Fails when something already listens on `port`, so readiness never comes from another server. */
async function ensureFree(port) {
  for (const host of ['127.0.0.1', '::1']) {
    await new Promise((ok, fail) => {
      const probe = createConnection({ port, host });
      probe.once('connect', () => {
        probe.destroy();
        fail(new Error(`port ${port} is already in use on ${host}`));
      });
      probe.once('error', () => ok());
    });
  }
}

async function waitFor(url, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (stopping) throw new Error('stack is stopping');
    try {
      const res = await fetch(url);
      if (res.ok) return;
    } catch {
      // not listening yet
    }
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error(`${url} did not answer within ${timeoutMs / 1000} s`);
}

function kill(child) {
  if (child.exitCode !== null || child.signalCode !== null) return Promise.resolve();
  const exited = new Promise((r) => child.once('exit', r));
  if (isWindows) spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], { stdio: 'ignore' });
  else child.kill('SIGTERM');
  return exited;
}

async function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  log('stopping');
  await Promise.all(children.map(kill));
  if (postgres && postgres.exitCode === null) {
    const exited = new Promise((r) => postgres.once('exit', r));
    postgres.stdin.end();
    const timer = setTimeout(() => void kill(postgres), 20_000);
    await exited;
    clearTimeout(timer);
  }
  log('stopped');
  process.exit(code);
}

async function main() {
  process.on('SIGINT', () => void stop(0));
  process.on('SIGTERM', () => void stop(0));
  if (process.send) {
    process.on('message', (m) => m === 'stop' && void stop(0));
    process.on('disconnect', () => void stop(0));
  }

  await ensureFree(apiPort);
  await ensureFree(studioPort);
  const py = python();
  const databaseUrl = process.env.ONTAIX_DATABASE_URL || (await startPostgres(py));
  const studioOrigins = [`http://localhost:${studioPort}`, `http://127.0.0.1:${studioPort}`];
  const apiEnv = {
    ...process.env,
    ONTAIX_ENVIRONMENT: 'dev',
    ONTAIX_DEV_IDENTITY_HEADER: process.env.ONTAIX_DEV_IDENTITY_HEADER ?? 'true',
    ONTAIX_ALLOWED_ORIGINS: process.env.ONTAIX_ALLOWED_ORIGINS || JSON.stringify(studioOrigins),
    ONTAIX_DATABASE_URL: databaseUrl,
    ONTAIX_SEED: process.env.ONTAIX_SEED || 'empty',
  };
  seed(py, apiEnv);
  process.send?.({ type: 'database', url: databaseUrl });

  // psycopg's async driver needs a selector loop; uvicorn picks the proactor loop on Windows.
  const loop = isWindows ? ['--loop', 'asyncio:SelectorEventLoop'] : [];
  start('api', py, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(apiPort), ...loop], {
    cwd: apiDir,
    env: apiEnv,
  });
  await waitFor(`${apiUrl}/healthz`, 60_000);
  log(`API ready at ${apiUrl}`);

  const vite = join(studioDir, 'node_modules', 'vite', 'bin', 'vite.js');
  start('studio', process.execPath, [vite, '--host', '127.0.0.1', '--port', String(studioPort), '--strictPort'], {
    cwd: studioDir,
    env: {
      ...process.env,
      VITE_ONTAIX_API_URL: '/api/v1',
      VITE_ONTAIX_DEV_USER: process.env.VITE_ONTAIX_DEV_USER ?? 'demo@northwind.com',
      ONTAIX_API_PROXY: apiUrl,
    },
  });
  await waitFor(studioUrl, 60_000);
  log(`ready: Studio ${studioUrl} against the API ${apiUrl}`);
  process.send?.('ready');
}

main().catch((err) => {
  if (stopping) return;
  log(`failed: ${err.message}`);
  void stop(1);
});
