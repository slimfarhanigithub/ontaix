/**
 * Test helper: a `fetch` stub that answers routes of the API by `METHOD /path` and records every
 * call with its headers and body. Session fixtures carry an obviously fake CSRF token built at
 * runtime; no test here holds a real credential.
 */
import type { Session } from '../api/types';

export interface Recorded {
  method: string;
  path: string;
  headers: Record<string, string>;
  body: unknown;
}

export type Answer = Response | Error | ((call: Recorded) => Response | Error);

export interface FetchStub {
  calls: Recorded[];
  /** Replaces or adds a route. */
  on(route: string, answer: Answer): void;
  /** The calls made to one route, oldest first. */
  to(route: string): Recorded[];
}

export const json = (status: number, body: unknown, headers: Record<string, string> = {}): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json', ...headers } });

export const problem = (status: number, code: string, detail: string, headers: Record<string, string> = {}): Response =>
  json(status, { type: `urn:ontaix:problem:${code}`, title: code, status, code, detail }, headers);

export const noContent = (): Response => new Response(null, { status: 204 });

export const CSRF = 'test-csrf-'.padEnd(43, 'x');

export function session(over: Partial<Session> = {}): Session {
  return {
    kind: 'member',
    account: { id: 'acc-1', email: 'ana@acme.example', name: 'Ana' },
    organization: { id: 'org-1', name: 'Acme', slug: 'acme' },
    userId: 'u-1',
    support: null,
    acting: null,
    csrfToken: CSRF,
    mustChangePassword: false,
    idleExpiresAt: '2026-09-30T10:00:00Z',
    absoluteExpiresAt: '2026-09-30T21:00:00Z',
    ...over,
  };
}

export function platformSession(over: Partial<Session> = {}): Session {
  return session({ kind: 'platform', account: { id: 'acc-sa', email: 'admin@platform.example', name: 'Admin' }, organization: null, userId: null, platformRoles: ['super_admin'], ...over });
}

/** Installs the stub on `window.fetch` for the test; `vi.unstubAllGlobals()` removes it. */
export function stubFetch(routes: Record<string, Answer> = {}): FetchStub {
  const table = new Map(Object.entries(routes));
  const calls: Recorded[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const path = new URL(url, 'http://studio.test').pathname.replace(/^\/api\/v1/, '');
    const method = (init?.method || 'GET').toUpperCase();
    const headers: Record<string, string> = {};
    new Headers(init?.headers).forEach((v, k) => {
      headers[k.toLowerCase()] = v;
    });
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) : init?.body;
    const call = { method, path, headers, body };
    calls.push(call);
    const answer = table.get(`${method} ${path}`);
    const res = typeof answer === 'function' ? answer(call) : answer;
    if (res instanceof Error) throw res;
    if (!res) return problem(404, 'not_found', `${method} ${path} is not stubbed`);
    return res.clone();
  });
  vi.stubGlobal('fetch', fetchMock);
  return {
    calls,
    on: (route, answer) => void table.set(route, answer),
    to: (route) => calls.filter((c) => `${c.method} ${c.path}` === route),
  };
}
