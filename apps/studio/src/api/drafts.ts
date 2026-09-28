/**
 * Drafts in the contract's shape. The contract takes a concept or spec parent, and each end of a
 * relation, by id or by label, never both; the Studio's senders pass both, so a present id wins
 * and an empty id gives way to the label.
 */
import type { ProposalDraft } from './types';

export function contractDraft(draft: ProposalDraft): ProposalDraft {
  if (draft.type === 'concept' || draft.type === 'spec') {
    const { parentId, parentLabel, ...rest } = draft;
    return (parentId ? { ...rest, parentId } : { ...rest, parentLabel }) as ProposalDraft;
  }
  if (draft.type === 'relation') {
    const { aId, bId, aLabel, bLabel, ...rest } = draft;
    return {
      ...rest,
      ...(aId ? { aId } : { aLabel }),
      ...(bId ? { bId } : { bLabel }),
    } as ProposalDraft;
  }
  return draft;
}

/** The end of a relation draft that names neither or both of its id and label, if any. */
export function mixedRelationEnd(draft: ProposalDraft): 'a' | 'b' | null {
  if (draft.type !== 'relation') return null;
  if (!draft.aId === !draft.aLabel) return 'a';
  if (!draft.bId === !draft.bLabel) return 'b';
  return null;
}
