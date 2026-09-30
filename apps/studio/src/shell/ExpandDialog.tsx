/**
 * Expand: the model suggests concepts to grow from a cell, and the chosen ones become proposals
 * marked as suggestions. An owner addition absent from the reference, built from its own
 * `dialog()` frame, `.form` fields and `.chk` rows. Model text is rendered as text only.
 */
import { useState } from 'react';

import { api } from '../api/client';
import { ApiError, type ExpansionDraft, type ExpansionOutcome, type ExpansionResult } from '../api/types';
import type { Node } from '../canvas/types';
import { store } from '../store/store';
import { teachSessionId } from '../teach/teach';
import { BusyButton, useBusyAction } from './busy';
import { DialogFrame } from './Dialog';

export const EXPAND_SUB = 'The model suggests concepts to grow from it; each one is a proposal';
const DEPTHS = ['1', '2', '3', '4', '5'];
const FOCUS_MAX = 200;

/** True when the drawer offers Expand: an approved, live concept or company root the server knows. */
export const canExpandFromDrawer = (n: Node): boolean =>
  (n.kind === 'concept' || n.kind === 'root') && !n.pending && !n.dying && !!n.sid;

/** The toast body shown when an expansion returns no draft. */
export function noSuggestionsText(outcome: ExpansionOutcome): string {
  switch (outcome) {
    case 'rate_limited':
    case 'budget_exhausted':
      return 'The model budget is spent';
    case 'refused':
      return 'The model declined this request';
    case 'used':
      return 'Everything suggested is already in the model';
    default:
      return 'The model is not available';
  }
}

/** The draft indexes checked after `index` is checked or unchecked: unchecking takes every draft
 * that requires it, checking brings every draft it requires. */
export function toggleSelection(checked: Set<number>, requires: number[][], index: number): Set<number> {
  const next = new Set(checked);
  if (next.has(index)) {
    const drop = [index];
    while (drop.length) {
      const i = drop.pop() as number;
      if (!next.delete(i) && i !== index) continue;
      requires.forEach((req, j) => {
        if (next.has(j) && req.includes(i)) drop.push(j);
      });
    }
  } else {
    const add = [index];
    while (add.length) {
      const i = add.pop() as number;
      if (next.has(i)) continue;
      next.add(i);
      add.push(...(requires[i] || []));
    }
  }
  return next;
}

export function openExpandDialog(n: Node): void {
  store.openDialog({ render: (close) => <ExpandDialog node={n} close={close} /> });
}

/** The label of a draft's row: a concept's label, or a relation as `<from> <action> <to>`. */
export function draftTitle(d: ExpansionDraft, expanded: Node): string {
  if (d.type === 'concept') return d.label;
  const end = (id: string | undefined, label: string | undefined) => (id && id === expanded.sid ? expanded.label : label || '');
  return `${end(d.aId, d.aLabel)} ${d.action} ${end(d.bId, d.bLabel)}`;
}

/** The columns of a draft's row after its label: the link to what it grows from, the confidence and the note below. */
export function draftColumns(
  d: ExpansionDraft,
  note: ExpansionResult['notes'][number],
  expanded: Node,
): { verb: string; confidence: string; note: string } {
  const confidence = `${Math.round(note.confidence * 100)}%`;
  if (d.type !== 'concept') return { verb: 'relation', confidence, note: note.rationale };
  const parent = d.parentId && d.parentId === expanded.sid ? expanded.label : d.parentLabel || expanded.label;
  return { verb: `${d.action} ${parent}`, confidence, note: `level ${note.depth ?? 1} · ${note.rationale}` };
}

function ExpandDialog({ node, close }: { node: Node; close: () => void }) {
  const [depth, setDepth] = useState('');
  const [focus, setFocus] = useState('');
  const suggesting = useBusyAction();
  const [result, setResult] = useState<ExpansionResult | null>(null);
  const [checked, setChecked] = useState<Set<number>>(new Set());

  /** Asks the model; the drawer's Expand button waits with this dialog while it answers. */
  const suggest = async () => {
    if (!node.sid) return;
    store.ui.expanding = node;
    store.bump();
    const companyId = node.company?.sid;
    const text = focus.trim();
    try {
      const res = await api.expandConcept(node.sid, {
        ...(depth ? { depth: Number(depth) } : {}),
        ...(text ? { focus: text } : {}),
        ...(companyId ? { sessionId: teachSessionId(companyId) } : {}),
      });
      if (!res.drafts.length || !res.expansionId) {
        close();
        store.toast2('No suggestions', noSuggestionsText(res.llmOutcome));
        return;
      }
      setResult(res);
      setChecked(new Set(res.drafts.map((_, i) => i)));
    } catch (err) {
      close();
      if (err instanceof ApiError) store.refused(err);
      else throw err;
    } finally {
      store.ui.expanding = null;
      store.bump();
    }
  };

  const propose = async () => {
    if (!result?.expansionId || !checked.size) return;
    try {
      await api.proposeExpansion(
        result.expansionId,
        [...checked].sort((a, b) => a - b),
      );
      close();
    } catch (err) {
      close();
      if (err instanceof ApiError) store.refused(err);
      else throw err;
    }
  };

  if (!result) {
    return (
      <DialogFrame
        title={`Expand ${node.label}`}
        sub={EXPAND_SUB}
        onClose={close}
        footer={
          <>
            <button className="btn" onClick={close}>
              Cancel
            </button>
            <button
              className="btn primary"
              disabled={suggesting.shown}
              aria-busy={suggesting.shown ? 'true' : undefined}
              onClick={() => suggesting.run(suggest)}
            >
              {suggesting.shown ? <span className="spin"></span> : null}
              Suggest
            </button>
          </>
        }
      >
        {suggesting.shown ? (
          <div id="exWait">
            <span className="spin"></span>Expanding <b>{node.label}</b>…
          </div>
        ) : (
          <div className="form">
            <label>Depth</label>
            <select id="exDepth" value={depth} onChange={(e) => setDepth(e.currentTarget.value)}>
              <option value="">Any depth</option>
              {DEPTHS.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
            <label>Focus (optional)</label>
            <input
              id="exFocus"
              maxLength={FOCUS_MAX}
              placeholder="e.g. after-sales services"
              value={focus}
              onChange={(e) => setFocus(e.currentTarget.value)}
            />
          </div>
        )}
      </DialogFrame>
    );
  }

  const requires = result.notes.map((n) => n.requires);
  return (
    <DialogFrame
      title={`Expand ${node.label}`}
      sub={`${result.drafts.length} suggestions · ${result.skipped.length} skipped`}
      onClose={close}
      footer={
        <>
          <button className="btn" onClick={close}>
            Cancel
          </button>
          <BusyButton className="btn primary" disabled={!checked.size} onClick={propose}>
            {`Propose ${checked.size}`}
          </BusyButton>
        </>
      }
    >
      <div className="ex-list" role="group" aria-label={`Suggestions to grow from ${node.label}`}>
        <div className="ex-head" aria-hidden="true">
          <span></span>
          <span>Suggestion</span>
          <span>Link</span>
          <span>Confidence</span>
        </div>
        {result.drafts.map((d, i) => {
          const col = draftColumns(d, result.notes[i], node);
          return (
            <label className="chk ex-row" key={i}>
              <input
                type="checkbox"
                data-index={i}
                checked={checked.has(i)}
                onChange={() => setChecked((c) => toggleSelection(c, requires, i))}
              />
              <b className="ex-label">{draftTitle(d, node)}</b>
              <span className="ex-verb">{col.verb}</span>
              <span className="ex-conf">{col.confidence}</span>
              <small className="ex-note">{col.note}</small>
            </label>
          );
        })}
      </div>
    </DialogFrame>
  );
}
