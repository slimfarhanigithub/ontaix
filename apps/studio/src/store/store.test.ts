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
    ['approve', () => store.approve(proposal)],
    ['reject', () => store.reject(proposal)],
  ] as const)('%s answered 409 reloads the scene and its proposals without a toast', async (action, run) => {
    vi.spyOn(api, action).mockRejectedValue(refusal(409, 'proposal_decided'));
    const reload = vi.spyOn(store, 'reloadScene').mockResolvedValue();

    await run();

    expect(reload).toHaveBeenCalledTimes(1);
    expect(store.ui.toasts).toHaveLength(0);
  });

  it('a decision still busy after the client retry shows the toast', async () => {
    vi.spyOn(api, 'approve').mockRejectedValue(refusal(503, 'busy'));
    const reload = vi.spyOn(store, 'reloadScene').mockResolvedValue();

    await store.approve(proposal);

    expect(reload).not.toHaveBeenCalled();
    expect(store.ui.toasts.map((t) => t.strong)).toEqual(['Refused']);
  });
});
