import { api, busyRetryDelayMs, hasDevIdentity } from './client';
import { authSignals, forgetSession, rememberSession } from './session';
import { ApiError, type Session } from './types';

const busy = (retryAfter: string | null) =>
  new Response(JSON.stringify({ title: 'Busy', status: 503, code: 'busy', detail: 'try again' }), {
    status: 503,
    headers: retryAfter === null ? {} : { 'Retry-After': retryAfter },
  });
const ok = () => new Response(JSON.stringify({ items: [], page: 1, pageSize: 1, total: 0 }), { status: 200 });

describe('503 busy', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('waits Retry-After, capped at 3 s, and 1 s when it is missing', () => {
    expect(busyRetryDelayMs('1')).toBe(1000);
    expect(busyRetryDelayMs('10')).toBe(3000);
    expect(busyRetryDelayMs(null)).toBe(1000);
    expect(busyRetryDelayMs('soon')).toBe(1000);
  });

  it('retries once after Retry-After and returns the second answer', async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValueOnce(busy('2')).mockResolvedValueOnce(ok());
    vi.stubGlobal('fetch', fetchMock);

    const result = api.listProposals();
    await vi.advanceTimersByTimeAsync(1999);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);

    await expect(result).resolves.toMatchObject({ total: 0 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('gives up after one retry with the busy problem', async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValueOnce(busy('1')).mockResolvedValueOnce(busy('1'));
    vi.stubGlobal('fetch', fetchMock);

    const result = api.approve('p1').catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(1000);
    const err = await result;

    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).problem.code).toBe('busy');
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe('session headers', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    forgetSession();
  });

  it('sends the CSRF token on unsafe calls, uploads included, never on GET, and the cookie with every call', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(ok()));
    vi.stubGlobal('fetch', fetchMock);
    rememberSession({ csrfToken: 'csrf-'.padEnd(43, 'x') } as Session);

    await api.listProposals();
    await api.approve('p1');
    await api.importSentences(new File(['a sentence.'], 'a.txt', { type: 'text/plain' }));
    await api.proposeUnbind('b1');

    const [get, post, upload, del] = fetchMock.mock.calls.map((c) => c[1] as RequestInit);
    for (const init of [get, post, upload, del]) expect(init.credentials).toBe('same-origin');
    expect(new Headers(get.headers).get('X-CSRF-Token')).toBeNull();
    expect(new Headers(post.headers).get('X-CSRF-Token')).toBe('csrf-'.padEnd(43, 'x'));
    expect(new Headers(upload.headers).get('X-CSRF-Token')).toBe('csrf-'.padEnd(43, 'x'));
    expect(upload.body).toBeInstanceOf(FormData);
    expect(new Headers(del.headers).get('X-CSRF-Token')).toBe('csrf-'.padEnd(43, 'x'));
  });

  it('sends no identity header unless a dev user is chosen', async () => {
    const fetchMock = vi.fn().mockResolvedValue(ok());
    vi.stubGlobal('fetch', fetchMock);
    await api.listProposals();
    expect(hasDevIdentity()).toBe(false);
    expect(new Headers((fetchMock.mock.calls[0][1] as RequestInit).headers).get('X-Ontaix-User')).toBeNull();
  });

  it('raises the session signals from 401 and 403 password_change_required, but not from sign-in', async () => {
    const seen: string[] = [];
    const off = authSignals.subscribe((s) => seen.push(s));
    const refuse = (status: number, code: string) =>
      new Response(JSON.stringify({ title: code, status, code }), { status, headers: { 'content-type': 'application/problem+json' } });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(refuse(401, 'invalid_credentials'))
      .mockResolvedValueOnce(refuse(403, 'password_change_required'))
      .mockResolvedValueOnce(refuse(401, 'unauthorized'));
    vi.stubGlobal('fetch', fetchMock);
    await expect(api.signIn({ email: 'a@b.example', password: 'not-a-real-password' })).rejects.toBeInstanceOf(ApiError);
    await expect(api.listProposals()).rejects.toBeInstanceOf(ApiError);
    await expect(api.listProposals()).rejects.toBeInstanceOf(ApiError);
    off();
    expect(seen).toEqual(['passwordChangeRequired', 'ended']);
  });
});
