/**
 * The Governance group of the admin portal: Audit log and Cost management (`pageAudit` and
 * `pageAgents`, reference lines 1030-1036). Audit and cost data come from the API; an
 * unavailable endpoint leaves the page empty. Cost management shows the month's language model
 * and OCR usage of the tenant, `GET /cost`'s `llm` block: calls, tokens against the monthly token
 * cap, OCR pages against the monthly page cap, the estimated cost and the breakdown by purpose.
 */
import { useEffect, useState } from 'react';

import { api } from '../../api/client';
import type { CostSummary, LlmPurpose } from '../../api/types';
import { useStore } from '../../shell/dom';
import { directory, failed } from '../adminData';
import { en } from '../listModel';

/** The purposes in the order the table lists them, with their labels. */
export const PURPOSE_LABEL: Record<LlmPurpose, string> = {
  teach_extraction: 'Teach extraction',
  concept_expansion: 'Concept expansion',
  document_extraction: 'Document extraction',
  document_ocr: 'Document OCR',
};

/** An amount in euro with two decimals, `€ 1.87`. */
export const eur = (n: number): string => `€ ${n.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export function AuditLog() {
  useStore();
  const rows = directory.audit;
  return (
    <>
      <h2>Audit log</h2>
      <p className="lead">Every approval, rejection, setting change and connection, append-only.</p>
      <div className="log">
        {rows.length ? (
          rows.map((e) => (
            <div key={e.id}>
              <span>{new Date(e.at).toLocaleTimeString('en-GB')}</span>
              <span>{e.kind}</span>
              <span>{e.actor.platformAccountId ? `${e.what} · platform super admin` : e.what}</span>
              <span className={e.ok ? 'ok' : 'no'}>{e.ok ? 'approved' : 'rejected'}</span>
            </div>
          ))
        ) : (
          <div>
            <span></span>
            <span></span>
            <span style={{ color: 'var(--ink-3)' }}>Nothing yet.</span>
            <span></span>
          </div>
        )}
      </div>
    </>
  );
}

/** Loads one API resource each time the portal renders from scratch; a failure leaves it null. `load` must be stable. */
function useAdminResource<T>(load: () => Promise<T>): T | null {
  const st = useStore();
  const [value, setValue] = useState<T | null>(null);
  const rev = st.ui.adminRev;
  useEffect(() => {
    let live = true;
    load().then(
      (v) => {
        if (live) setValue(v);
      },
      (err: unknown) => failed(err, 'Unavailable'),
    );
    return () => {
      live = false;
    };
  }, [rev, load]);
  return value;
}

const loadCost = () => api.getCost();

/** The caption under a used count: the monthly cap it counts against, or that a cap of 0 turned the step off. */
export const capText = (cap: number, unit: string, off: string): string => (cap ? `${unit} of ${en(cap)} this month` : `${unit} · ${off}`);

export function CostManagement() {
  const cost: CostSummary | null = useAdminResource(loadCost);
  const llm = cost ? cost.llm : null;
  const rows = llm ? llm.byPurpose : [];
  return (
    <>
      <h2>Cost management</h2>
      <p className="lead">
        What the model costs this month: every sentence, suggestion and document read by the language model, and every scanned page the OCR read,
        measured against the tenant’s monthly caps.
      </p>
      <div className="kpis">
        <div>
          <b>{en(llm ? llm.calls : 0)}</b>
          <span>model calls this month</span>
        </div>
        <div>
          <b>{en(llm ? llm.tokensUsed : 0)}</b>
          <span>{capText(llm ? llm.tokenCap : 0, 'tokens', 'the model step is off')}</span>
        </div>
        <div>
          <b>{en(llm ? llm.ocrPagesUsed : 0)}</b>
          <span>{capText(llm ? llm.ocrPageCap : 0, 'OCR pages', 'OCR is off')}</span>
        </div>
        <div>
          <b>{eur(llm ? llm.costEur : 0)}</b>
          <span>{`estimated · ${en(llm ? llm.inputTokens : 0)} in · ${en(llm ? llm.outputTokens : 0)} out`}</span>
        </div>
      </div>
      <h3>By purpose</h3>
      <table className="tbl">
        <thead>
          <tr>
            <th>Purpose</th>
            <th className="num">Calls</th>
            <th className="num">Pages</th>
            <th className="num">Cost · month</th>
          </tr>
        </thead>
        <tbody>
          {rows.length ? (
            rows.map((p) => (
              <tr key={p.purpose}>
                <td>
                  <b>{PURPOSE_LABEL[p.purpose] || p.purpose}</b>
                </td>
                <td className="num">{en(p.calls)}</td>
                <td className="num">{p.pages === undefined || p.pages === null ? '—' : en(p.pages)}</td>
                <td className="num">{eur(p.costEur)}</td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={4} style={{ color: 'var(--ink-3)' }}>
                No model call this month.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </>
  );
}
