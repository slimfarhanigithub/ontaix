/**
 * Routes `fetch` calls under the API base path to the in-browser mock server. Everything else
 * goes to the network untouched.
 *
 * The answer is a Response-shaped object whose `json()` resolves in a microtask. A real
 * `Response` reads its body in a later task, and under a fake clock that gap lets a frame run
 * between two proposals of one teach batch, which the reference never does. A multipart upload
 * (`POST /import/detect`, `POST /import/sentences`, `POST /ontology-imports`) is read from its
 * form before the mock answers.
 */
import { createMockServer, type MockResponse, type MockServer } from './server';

export function installMockFetch(base = '/api/v1', server: MockServer = createMockServer()): MockServer {
  const realFetch = window.fetch.bind(window);
  window.fetch = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const u = new URL(url, location.origin);
    if (!u.pathname.startsWith(base)) return realFetch(input, init);
    const method = (init?.method || (typeof input === 'object' && 'method' in input ? input.method : 'GET') || 'GET').toUpperCase();
    if (init?.body instanceof FormData) return upload(server, u.pathname.slice(base.length), init.body);
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    return Promise.resolve(answer(server.handle(method, u.pathname.slice(base.length) + u.search, body)));
  };
  return server;
}

async function upload(server: MockServer, path: string, form: FormData): Promise<Response> {
  const file = form.get('file');
  if (!(file instanceof Blob)) return answer(server.handle('POST', path, {}));
  const name = file instanceof File ? file.name : '';
  const received = { name, type: file.type, bytes: new Uint8Array(await file.arrayBuffer()) };
  const fields: Record<string, string> = {};
  form.forEach((value, key) => {
    if (typeof value === 'string') fields[key] = value;
  });
  if (path === '/ontology-imports') return answer(await server.importOntology(received, fields));
  if (path === '/import/detect') return answer(await server.detectImport(received));
  return answer(await server.importDocument(received, fields));
}

function answer(res: MockResponse): Response {
  const text = JSON.stringify(res.body);
  return {
    ok: res.status >= 200 && res.status < 300,
    status: res.status,
    statusText: '',
    headers: new Headers({ 'content-type': res.status >= 400 ? 'application/problem+json' : 'application/json' }),
    json: () => Promise.resolve(JSON.parse(text)),
    text: () => Promise.resolve(text),
  } as unknown as Response;
}
