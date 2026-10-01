/**
 * In-place edit of a pending draft in the changes panel, an owner addition
 * absent from the reference: a pending concept's label and birth action, a specialisation's
 * label, a relation's action, sent as `PATCH /proposals/{id}` at the revision the editor saw.
 * The proposal is not approved by the edit; it is still approved or rejected as a whole. The
 * fields use the reference's `.form` inputs and the row's `.act` buttons. Hidden from the
 * screenshot suite.
 */
import { useEffect, useRef, useState } from 'react';

import type { Proposal } from '../api/types';
import { BusyButton } from './busy';
import { useStore } from './dom';

/** Which fields of a pending draft can be edited; null when it cannot be edited. */
export function editableFields(p: Proposal): { label: boolean; action: boolean } | null {
  if (p.state !== 'pending') return null;
  if (p.type === 'concept') return { label: true, action: true };
  if (p.type === 'spec') return { label: true, action: false };
  if (p.type === 'relation') return { label: false, action: true };
  return null;
}

/** The action of a pending concept's birth relation or of a pending relation. */
export const currentAction = (p: Proposal): string => p.artefacts?.relations?.[0]?.label ?? '';

export function PendingEdit({ p: current, onDone }: { p: Proposal; onDone: () => void }) {
  const st = useStore();
  /** The proposal as the editor opened it: its revision is the one the save carries, so an edit made elsewhere meanwhile is refused, never overwritten. */
  const [p] = useState(current);
  const fields = editableFields(p) || { label: false, action: false };
  const [label, setLabel] = useState(p.title);
  const [action, setAction] = useState(currentAction(p));
  const first = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const t = setTimeout(() => first.current?.focus(), 30);
    return () => clearTimeout(t);
  }, []);

  const save = async () => {
    const patch: { label?: string; action?: string } = {};
    if (fields.label && label.trim() && label.trim() !== p.title) patch.label = label.trim();
    if (fields.action && action.trim() && action.trim().toLowerCase() !== currentAction(p)) patch.action = action.trim().toLowerCase();
    if (!Object.keys(patch).length) {
      onDone();
      return;
    }
    if (await st.editProposal(p, patch)) {
      onDone();
      return;
    }
    // Edited elsewhere meanwhile: the panel holds the newer text, so the stale editor closes.
    const now = st.ui.proposals.find((q) => q.id === p.id);
    if (!now || (now.revision ?? 0) !== (p.revision ?? 0)) onDone();
  };
  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      void save();
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      onDone();
    }
  };
  return (
    <>
      <div className="form" data-ox-new="" style={{ gridTemplateColumns: '1fr', margin: '6px 0 0' }}>
        {fields.label ? (
          <input ref={first} aria-label="Label" placeholder="label" maxLength={120} value={label} onChange={(e) => setLabel(e.target.value)} onKeyDown={onKey} />
        ) : null}
        {fields.action ? (
          <input
            ref={fields.label ? undefined : first}
            aria-label="Action"
            placeholder="action, e.g. produces"
            maxLength={60}
            value={action}
            onChange={(e) => setAction(e.target.value)}
            onKeyDown={onKey}
          />
        ) : null}
      </div>
      <div className="act" data-ox-new="">
        <BusyButton className="ok" onClick={save}>
          Save
        </BusyButton>
        <button onClick={onDone}>Cancel</button>
      </div>
    </>
  );
}
