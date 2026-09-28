import { contractDraft, mixedRelationEnd } from './drafts';
import type { ProposalDraft } from './types';

describe('contract drafts', () => {
  it('keeps a relation end id and drops its label', () => {
    const draft: ProposalDraft = { type: 'relation', aId: 'a1', bId: 'b1', aLabel: 'Plant', bLabel: 'Line', action: 'runs' };
    expect(contractDraft(draft)).toEqual({ type: 'relation', aId: 'a1', bId: 'b1', action: 'runs' });
    expect(mixedRelationEnd(contractDraft(draft))).toBeNull();
  });

  it('keeps an equivalence draft by ids across companies', () => {
    const draft: ProposalDraft = { type: 'relation', aId: 'a1', bId: 'b2', aLabel: 'Customer', bLabel: 'Client', action: 'equivalent to', seed: 0.5 };
    expect(contractDraft(draft)).toEqual({ type: 'relation', aId: 'a1', bId: 'b2', action: 'equivalent to', seed: 0.5 });
  });

  it('keeps the label of an end without an id', () => {
    const draft = { type: 'relation', aId: '', bId: 'b1', aLabel: 'Plant', bLabel: 'Line', action: 'runs' } as ProposalDraft;
    expect(contractDraft(draft)).toEqual({ type: 'relation', aLabel: 'Plant', bId: 'b1', action: 'runs' });
  });

  it('keeps a concept parent id over its label, and the label when the id is empty', () => {
    const base = { type: 'concept', companyId: 'c', label: 'Plant', domainKey: 'production' } as const;
    expect(contractDraft({ ...base, parentId: 'p', parentLabel: 'Root' } as ProposalDraft)).toEqual({ ...base, parentId: 'p' });
    expect(contractDraft({ ...base, parentId: '', parentLabel: 'Root' } as ProposalDraft)).toEqual({ ...base, parentLabel: 'Root' });
  });

  it('names the end of a relation that carries both an id and a label', () => {
    expect(mixedRelationEnd({ type: 'relation', aId: 'a', bId: 'b', aLabel: 'A', action: 'x' })).toBe('a');
    expect(mixedRelationEnd({ type: 'relation', aId: 'a', bId: 'b', bLabel: 'B', action: 'x' })).toBe('b');
  });
});
