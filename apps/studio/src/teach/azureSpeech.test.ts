import { createScene } from '../canvas/state';
import type { Company, Domain, Node } from '../canvas/types';
import { FakeRecognizer, fakeSpeechSdk, resetFakeRecognizer } from './speechSdkFake';

const TOKEN = {
  token: 'aad#/subscriptions/s/resourceGroups/rg/providers/Microsoft.CognitiveServices/accounts/spch#eyJ.token',
  region: 'francecentral',
  expiresAt: '2026-09-29T23:00:00Z',
  language: 'en-GB' as const,
};

function handlers() {
  return { started: vi.fn(), interim: vi.fn(), final: vi.fn(), ended: vi.fn(), failed: vi.fn() };
}

async function load() {
  vi.resetModules();
  resetFakeRecognizer();
  vi.doMock('microsoft-cognitiveservices-speech-sdk', () => fakeSpeechSdk());
  const { api } = await import('../api/client');
  const { ApiError } = await import('../api/types');
  const speech = await import('./azureSpeech');
  return { api, ApiError, ...speech };
}

describe('Azure Speech recognition', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.doUnmock('microsoft-cognitiveservices-speech-sdk');
  });

  it('starts continuous recognition with the API token, its region, en-GB and the phrase list', async () => {
    const { api, startAzureSpeech } = await load();
    const token = vi.spyOn(api, 'speechToken').mockResolvedValue(TOKEN);
    const h = handlers();

    const recording = await startAzureSpeech('company-a', ['Insight', 'ADNOC', 'L&S'], h);

    const rec = FakeRecognizer.last as FakeRecognizer;
    expect(token).toHaveBeenCalledWith('company-a');
    expect(rec.config).toEqual({ token: TOKEN.token, region: 'francecentral', speechRecognitionLanguage: 'en-GB' });
    expect(rec.phrases).toEqual(['Insight', 'ADNOC', 'L&S']);
    expect(rec.started).toBe(true);
    expect(h.started).toHaveBeenCalledTimes(1);
    expect(recording).not.toBeNull();
  });

  it('reports words being recognised, finished sentences, and the words never finished on stop', async () => {
    const { api, startAzureSpeech } = await load();
    vi.spyOn(api, 'speechToken').mockResolvedValue(TOKEN);
    const h = handlers();
    const recording = await startAzureSpeech('company-a', [], h);
    const rec = FakeRecognizer.last as FakeRecognizer;

    rec.hearing('Insight sells');
    rec.heard('Insight sells services.');
    rec.hearing('They focus');
    recording?.stop();

    expect(h.interim.mock.calls).toEqual([['Insight sells'], ['They focus']]);
    expect(h.final.mock.calls).toEqual([['Insight sells services.']]);
    expect(h.ended.mock.calls).toEqual([['They focus']]);
    expect(h.failed).not.toHaveBeenCalled();
    expect(rec.closed).toBe(true);
  });

  it('falls back without loading the SDK when the API answers 503 or the network fails', async () => {
    const { api, ApiError, startAzureSpeech } = await load();
    const token = vi.spyOn(api, 'speechToken');
    token.mockRejectedValueOnce(new ApiError(503, { title: 'Unavailable', status: 503, code: 'unavailable' }));
    token.mockRejectedValueOnce(new TypeError('Failed to fetch'));

    expect(await startAzureSpeech('company-a', [], handlers())).toBeNull();
    expect(await startAzureSpeech('company-a', [], handlers())).toBeNull();
    expect(FakeRecognizer.last).toBeNull();
  });

  it('throws refusals the speaker must see instead of falling back', async () => {
    const { api, ApiError, startAzureSpeech } = await load();
    const refusal = new ApiError(409, { title: 'Channel disabled', status: 409, code: 'channel_disabled' });
    vi.spyOn(api, 'speechToken').mockRejectedValue(refusal);

    await expect(startAzureSpeech('company-a', [], handlers())).rejects.toBe(refusal);
  });

  it('falls back when the SDK cannot start, and hands over to the browser when it cancels with an error', async () => {
    const { api, startAzureSpeech } = await load();
    vi.spyOn(api, 'speechToken').mockResolvedValue(TOKEN);
    FakeRecognizer.failStart = true;
    const early = handlers();

    expect(await startAzureSpeech('company-a', [], early)).toBeNull();
    expect((FakeRecognizer.last as FakeRecognizer).closed).toBe(true);
    expect(early.started).not.toHaveBeenCalled();

    FakeRecognizer.failStart = false;
    const late = handlers();
    await startAzureSpeech('company-a', [], late);
    (FakeRecognizer.last as FakeRecognizer).hearing('Insight');
    (FakeRecognizer.last as FakeRecognizer).fail();

    expect(late.ended.mock.calls).toEqual([['Insight']]);
    expect(late.failed).toHaveBeenCalledTimes(1);
  });

  it('sets a fresh token on the running recogniser five minutes before the current one expires', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-09-29T22:00:00Z'));
    const { api, startAzureSpeech } = await load();
    const next = { ...TOKEN, token: 'aad#/subscriptions/s#eyJ.next', expiresAt: '2026-09-29T23:30:00Z' };
    const token = vi.spyOn(api, 'speechToken').mockResolvedValueOnce(TOKEN).mockResolvedValueOnce(next);
    await startAzureSpeech('company-a', [], handlers());
    const rec = FakeRecognizer.last as FakeRecognizer;

    await vi.advanceTimersByTimeAsync(54 * 60_000);
    expect(token).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(60_000);

    expect(token).toHaveBeenCalledTimes(2);
    expect(rec.authorizationToken).toBe(next.token);
  });
});

describe('the phrase list', () => {
  function scene() {
    const s = createScene();
    const company = { name: 'Insight', key: 'insight' } as Company;
    const other = { name: 'Aurora', key: 'aurora' } as Company;
    const sales = { key: 'sales' } as Domain;
    let order = 0;
    const node = (label: string, extra: Partial<Node> = {}): Node => {
      const n = { label, kind: 'concept', company, domain: null, dying: null, bornAt: new Date(Date.UTC(2026, 0, 1, 0, order++)), ...extra } as Node;
      s.nodes.push(n);
      return n;
    };
    s.activeCompany = company;
    return { s, company, other, sales, node };
  }

  it('lists the company name, then focused labels, then the most recently born, once each', async () => {
    const { speechPhrases } = await load();
    const { s, other, sales, node } = scene();
    node('Insight', { kind: 'root' });
    node('Customer');
    node('Order', { domain: sales });
    node('Invoice');
    node('customer', { pending: true });
    node('Supplier', { company: other });
    node('Retired', { dying: { start: 0 } });
    node('Data platform', { kind: 'source' });
    s.focusDomain = sales;

    expect(speechPhrases(s)).toEqual(['Insight', 'Order', 'customer', 'Invoice']);
  });

  it('puts the focused cell neighbourhood first, skips labels over 120 characters and stops at 500', async () => {
    const { speechPhrases, MAX_PHRASES } = await load();
    const { s, node } = scene();
    const focused = node('Plant');
    node('x'.repeat(121));
    for (let i = 0; i < 600; i++) node(`Label ${i}`);
    s.stickyFocus = new Set([focused]);

    const phrases = speechPhrases(s);

    expect(phrases).toHaveLength(MAX_PHRASES);
    expect(phrases.slice(0, 3)).toEqual(['Insight', 'Plant', 'Label 599']);
    expect(phrases.some((p) => p.length > 120)).toBe(false);
  });
});
