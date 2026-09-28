import { api } from '../api/client';
import { ApiError, type Proposal } from '../api/types';
import { store } from './store';

const proposal = { id: 'p1', ready: true, title: 'Plant' } as Proposal;
const refusal = (status: number, code: string) => new ApiError(status, { title: code, status, code, detail: `${code} detail` });

describe('decision refusals', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    store.ui.toasts = [];
  });

  it.each([
    ['approve', 'proposal_decided', () => store.approve(proposal)],
    ['approve', 'proposal_not_ready', () => store.approve(proposal)],
    ['reject', 'proposal_decided', () => store.reject(proposal)],
  ] as const)('%s answered 409 %s reloads the scene and its proposals without a toast', async (action, code, run) => {
    vi.spyOn(api, action).mockRejectedValue(refusal(409, code));
    const reload = vi.spyOn(store, 'reloadScene').mockResolvedValue();

    await run();

    expect(reload).toHaveBeenCalledTimes(1);
    expect(store.ui.toasts).toHaveLength(0);
  });

  it.each(['same_approver', 'duplicate_label'])('any other 409 (%s) shows the toast and does not reload', async (code) => {
    vi.spyOn(api, 'approve').mockRejectedValue(refusal(409, code));
    const reload = vi.spyOn(store, 'reloadScene').mockResolvedValue();

    await store.approve(proposal);

    expect(reload).not.toHaveBeenCalled();
    expect(store.ui.toasts.map((t) => [t.strong, t.text])).toEqual([['Refused', `${code} detail`]]);
  });

  it('a decision still busy after the client retry shows the toast', async () => {
    vi.spyOn(api, 'approve').mockRejectedValue(refusal(503, 'busy'));
    const reload = vi.spyOn(store, 'reloadScene').mockResolvedValue();

    await store.approve(proposal);

    expect(reload).not.toHaveBeenCalled();
    expect(store.ui.toasts.map((t) => t.strong)).toEqual(['Refused']);
  });
});
