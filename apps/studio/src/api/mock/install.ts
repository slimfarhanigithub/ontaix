/**
 * Routes `fetch` calls under the API base path to the in-browser mock server. Everything else
 * goes to the network untouched.
 *
 * The answer is a Response-shaped object whose `json()` resolves in a microtask. A real
 * `Response` reads its body in a later task, and under a fake clock that gap lets a frame run
 * between two proposals of one story scene, which the reference never does.
 */
import { createMockServer, type MockServer } from './server';

export function installMockFetch(base = '/api/v1', server: MockServer = createMockServer()): MockServer {
  const realFetch = window.fetch.bind(window);
  window.fetch = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const u = new URL(url, location.origin);
    if (!u.pathname.startsWith(base)) return realFetch(input, init);
    const method = (init?.method || (typeof input === 'object' && 'method' in input ? input.method : 'GET') || 'GET').toUpperCase();
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    const res = server.handle(method, u.pathname.slice(base.length) + u.search, body);
    const text = JSON.stringify(res.body);
    const answer = {
      ok: res.status >= 200 && res.status < 300,
      status: res.status,
      statusText: '',
      headers: new Headers({ 'content-type': res.status >= 400 ? 'application/problem+json' : 'application/json' }),
      json: () => Promise.resolve(JSON.parse(text)),
      text: () => Promise.resolve(text),
    };
    return Promise.resolve(answer as unknown as Response);
  };
  return server;
}
