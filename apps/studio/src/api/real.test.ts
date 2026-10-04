import { api } from './client';
import { liveEvents, type Envelope } from './events';
import { connectRealApi } from './real';
import type { DecisionResult, Proposal } from './types';

const decision = (extra: Partial<Proposal>): DecisionResult =>
  ({
    proposal: { id: 'p1', type: 'change', state: 'approved', proposer: { kind: 'user' }, relationIds: [], bindingIds: [], ...extra },
    artefacts: {},
    cascaded: [],
    caption: null,
  }) as unknown as DecisionResult;

describe('decisions replayed from a real API', () => {
  const original = { ...api };
  let seen: Envelope['type'][] = [];
  let unsubscribe = () => {};

  beforeEach(() => {
    seen = [];
    unsubscribe = liveEvents.subscribe((e) => seen.push(e.type));
  });

  afterEach(() => {
    unsubscribe();
    Object.assign(api, original);
    vi.restoreAllMocks();
  });

  it('an approved new or edited domain is followed by snapshot.required, since its answer carries no domain', async () => {
    for (const changeKind of ['create_domain', 'edit_domain'] as const) {
      vi.spyOn(api, 'approve').mockResolvedValue(decision({ changeKind }));
      connectRealApi();
      await api.approve('p1', 0);
      Object.assign(api, original);
    }
    expect(seen).toEqual(['proposal.approved', 'snapshot.required', 'proposal.approved', 'snapshot.required']);
  });

  it('a move or a half approval is replayed alone; a second approval completing a domain change resyncs too', async () => {
    vi.spyOn(api, 'approve').mockResolvedValueOnce(decision({ changeKind: 'move_concept_domain' })).mockResolvedValueOnce(decision({ changeKind: 'create_domain', state: 'pending' }));
    vi.spyOn(api, 'secondApprove').mockResolvedValue(decision({ changeKind: 'create_domain' }));
    connectRealApi();
    await api.approve('p1', 0);
    await api.approve('p1', 0);
    await api.secondApprove('p1', 1);
    expect(seen).toEqual(['proposal.approved', 'proposal.half_approved', 'proposal.approved', 'snapshot.required']);
  });
});
