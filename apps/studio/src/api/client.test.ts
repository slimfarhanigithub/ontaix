import { api, busyRetryDelayMs } from './client';
import { ApiError } from './types';

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
