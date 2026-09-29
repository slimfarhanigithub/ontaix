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

  it('a 403 shows the refusal reason the API gives, as text', async () => {
    const forbidden = new ApiError(403, { title: 'Forbidden', status: 403, code: 'forbidden', detail: 'Only a Governor or Owner can approve' });
    vi.spyOn(api, 'approve').mockRejectedValue(forbidden);

    await store.approve(proposal);

    expect(store.ui.toasts.map((t) => [t.strong, t.text])).toEqual([['Refused', 'Only a Governor or Owner can approve']]);
  });

  it('a refusal without a detail shows its title', async () => {
    vi.spyOn(api, 'approve').mockRejectedValue(new ApiError(409, { title: 'Same approver', status: 409, code: 'same_approver' }));
    vi.spyOn(store, 'reloadScene').mockResolvedValue();

    await store.approve(proposal);

    expect(store.ui.toasts.map((t) => [t.strong, t.text])).toEqual([['Refused', 'Same approver']]);
  });

  it('a decision still busy after the client retry shows the toast', async () => {
    vi.spyOn(api, 'approve').mockRejectedValue(refusal(503, 'busy'));
    const reload = vi.spyOn(store, 'reloadScene').mockResolvedValue();

    await store.approve(proposal);

    expect(reload).not.toHaveBeenCalled();
    expect(store.ui.toasts.map((t) => t.strong)).toEqual(['Refused']);
  });
});
