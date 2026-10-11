/**
 * What the admin portal's buttons do, and the dialogs they open: settings, the typed `disable`
 * confirmation, rename, concept deletion, relation deletion and company removal. Behaviour and
 * copy from reference/ontaix-studio-reference.html lines 947-1053. Ontology changes are
 * proposals; settings changes are immediate. The ontology-editing dialogs (move to domain,
 * company removal named from the deletion impact, domain creation, edit and deletion, bulk
 * deletion) are owner additions in the same markup.
 */
import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react';

import { api } from '../api/client';
import type { DeletionImpact, DomainInput, DomainPatch, ProposalDraft, TenantDomain } from '../api/types';
import { NEUTRAL, PALETTE } from '../canvas/constants';
import type { Company, Domain, Link, Node } from '../canvas/types';
import { title } from '../nl/parser';
import { useBusyAction } from '../shell/busy';
import { DialogFrame } from '../shell/Dialog';
import { store } from '../store/store';
import { attempt, failed, invalidateDirectory } from './adminData';
import { conceptDeletion, deletionText, impactText } from './conceptDeletion';

/** Most concepts and domain products one bulk deletion may name. */
export const BULK_CONCEPTS = 200;
export const BULK_PRODUCTS = 20;
import { isDisableConfirmed } from './confirmText';
import type { SettingKey } from './Toggle';

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

/** Re-reads the audit log and redraws the portal from scratch. */
export function renderAdmin(): void {
  invalidateDirectory();
  store.renderAdmin();
}

/** A small dialog with Cancel and one action button, the reference's `confirmDialog`. */
export function confirmDialog(heading: string, body: ReactNode, label: string, onYes: () => unknown, danger?: boolean): void {
  store.openDialog({
    title: heading,
    body,
    small: true,
    buttons: [
      { label: 'Cancel' },
      {
        label,
        cls: danger ? 'danger' : 'primary',
        onClick: () => {
          const r = onYes();
          if (r instanceof Promise) return r.then(() => undefined);
        },
      },
    ],
  });
}

/**
 * Sends a draft; the success feedback runs only once the server has accepted it. A refusal
 * shows the store's refusal toast instead.
 */
function proposeThen(draft: ProposalDraft, accepted: () => void): Promise<void> {
  return store.propose(draft).then((p) => {
    if (p) accepted();
  }, failed);
}

/** Runs a proposal-creating call; the success feedback runs only when it was accepted. */
function attemptThen<T>(call: () => Promise<T>, accepted: () => void): Promise<void> {
  return attempt(call).then((r) => {
    if (r !== null) accepted();
  });
}

// ------------------------------------------------------------ settings

/** Flips a tenant setting; turning off "Companies may interact" goes through the typed confirmation. */
export function changeSetting(k: SettingKey): Promise<void> {
  const st = store.ui.settings;
  if (!st) return Promise.resolve();
  if (k === 'crossCompany' && st.crossCompany) return disableCrossCompany();
  return attempt(() => api.patchSettings({ [k]: !st[k] })).then((next) => {
    if (!next) return;
    store.ui.settings = next;
    store.applySettings();
    renderAdmin();
  });
}

const crossLinks = (): Link[] => store.s.links.filter((l) => l.a.company !== l.b.company && !l.dying);

/** With no cross-company relationship the switch turns off at once; otherwise the typed confirmation opens. */
function disableCrossCompany(): Promise<void> {
  const xl = crossLinks();
  const done = (removed: number) => {
    store.toast2('Disabled', `${plural(removed, 'cross-company relationship')} removed`);
    store.applySettings();
    renderAdmin();
  };
  if (!xl.length)
    return attempt(() => api.patchSettings({ crossCompany: false })).then((next) => {
      if (!next) return;
      store.ui.settings = next;
      done(0);
    });
  store.openDialog({
    render: (close) => (
      <CrossCompanyDialog
        links={xl}
        close={close}
        onConfirm={(typed) =>
          attempt(() => api.disableCrossCompany(typed)).then((res) => {
            if (!res) return;
            store.ui.settings = res.settings;
            done(res.removedRelations);
          })
        }
      />
    ),
  });
  return Promise.resolve();
}

function CrossCompanyDialog({ links, close, onConfirm }: { links: Link[]; close: () => void; onConfirm: (typed: string) => Promise<void> }) {
  const [typed, setTyped] = useState('');
  const [bad, setBad] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const ok = isDisableConfirmed(typed);
  const { shown, run } = useBusyAction();
  useEffect(() => {
    const t = setTimeout(() => input.current?.focus(), 40);
    return () => clearTimeout(t);
  }, []);
  const pairs = [...new Set(links.map((l) => `${l.a.company?.name} ↔ ${l.b.company?.name}`))];
  const submit = () => {
    if (!isDisableConfirmed(typed)) {
      setBad(true);
      input.current?.focus();
      return;
    }
    return onConfirm(typed.trim().toLowerCase()).then(close);
  };
  return (
    <DialogFrame
      title="Disable interaction between companies?"
      sub="this cannot be undone by re-enabling"
      onClose={close}
      footer={
        <>
          <button className="btn " data-i={0} onClick={close}>
            Cancel
          </button>
          <button
            className="btn danger"
            data-i={1}
            disabled={!ok || shown}
            aria-busy={shown ? 'true' : undefined}
            style={{ opacity: ok ? 1 : 0.5 }}
            onClick={() => run(submit)}
          >
            {shown ? <span className="spin"></span> : null}
            Disable and remove relationships
          </button>
        </>
      }
    >
      <p style={{ margin: '0 0 10px' }}>
        The companies below are already interacting. Disabling removes <b>{plural(links.length, 'relationship')}</b> between them, immediately and
        without a proposal. Each company keeps its own concepts and relations.
      </p>
      <p style={{ margin: '0 0 6px' }}>
        <b>{pairs.join(' · ')}</b>
      </p>
      <div className="discover" style={{ fontFamily: 'inherit', fontSize: '12.5px' }}>
        {links.slice(0, 6).map((l, i) => (
          <Fragment key={i}>
            {i ? <br /> : null}
            {`${l.a.label} `}
            <em style={{ color: 'var(--ink-3)', fontStyle: 'normal' }}>{l.label}</em>
            {` ${l.b.label}`}
          </Fragment>
        ))}
        {links.length > 6 ? (
          <div>
            <span>{`and ${links.length - 6} more`}</span>
          </div>
        ) : null}
      </div>
      <div className="form" style={{ marginTop: '14px', gridTemplateColumns: '1fr' }}>
        <label>
          Type <b style={{ color: 'var(--conflict)' }}>disable</b> to confirm
        </label>
        <input
          id="ccConfirm"
          ref={input}
          placeholder="disable"
          autoComplete="off"
          value={typed}
          style={bad ? { borderColor: 'var(--conflict)' } : undefined}
          onChange={(e) => {
            setTyped(e.target.value);
            setBad(false);
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && isDisableConfirmed(typed)) run(submit);
          }}
        />
      </div>
    </DialogFrame>
  );
}

// ------------------------------------------------------------ appearance

let colourTimer: ReturnType<typeof setTimeout> | null = null;

/** Applies a colour at once and saves it after the picker settles; the API takes lower-case hex only. */
export function changeColour(key: string, picked: string): void {
  const ap = store.ui.appearance;
  if (!ap) return;
  const value = picked.toLowerCase();
  const patch = key === '__accent' ? { accent: value } : { colors: { [key]: value } };
  store.ui.appearance = {
    ...ap,
    accent: key === '__accent' ? value : ap.accent,
    colors: key === '__accent' ? ap.colors : { ...ap.colors, [key]: value },
  };
  store.applyColors();
  if (colourTimer) clearTimeout(colourTimer);
  colourTimer = setTimeout(() => {
    colourTimer = null;
    void attempt(() => api.patchAppearance(patch));
  }, 300);
}

export function resetColours(): Promise<void> {
  return attempt(() => api.resetAppearance()).then((ap) => {
    if (!ap) return;
    store.ui.appearance = ap;
    store.applyColors();
    store.toast2('Reset', 'default colours');
    renderAdmin();
  });
}

// ------------------------------------------------------------ entities, relations

export function renameDialog(n: Node): void {
  store.openDialog({
    title: `Rename ${n.label}`,
    small: true,
    body: (
      <div className="form" style={{ gridTemplateColumns: '90px 1fr' }}>
        <label>New name</label>
        <input id="rnName" defaultValue={n.label} />
      </div>
    ),
    buttons: [
      { label: 'Cancel' },
      {
        label: 'Propose',
        cls: 'primary',
        onClick: (bk) => {
          const name = title((bk.querySelector<HTMLInputElement>('#rnName')?.value || '').trim());
          if (name && name !== n.label && n.sid)
            return proposeThen({ type: 'change', changeKind: 'rename', payload: { conceptId: n.sid, newLabel: name } }, () => {
              store.toast2('Proposed', `rename to ${name}`);
              renderAdmin();
            });
        },
      },
    ],
  });
}

/** Confirms deleting a concept, naming the descendants and relations that go with it; used by the drawer and Entities. */
export function deleteNodeDialog(n: Node): void {
  const { descendants, relations } = conceptDeletion(store.s, n);
  confirmDialog(
    `Delete ${n.label}?`,
    deletionText(
      descendants.map((d) => d.label),
      relations,
    ),
    'Propose deletion',
    () => {
      if (n.sid)
        return proposeThen({ type: 'change', changeKind: 'delete_concept', payload: { conceptId: n.sid } }, () => {
          store.toast2('Proposed', `deletion of ${n.label}`);
          renderAdmin();
        });
    },
    true,
  );
}

export function deleteRelationDialog(l: Link, name: string): void {
  confirmDialog(
    `Delete “${name}”?`,
    'This proposes a change for approval.',
    'Propose deletion',
    () => {
      if (l.sid)
        return proposeThen({ type: 'change', changeKind: 'remove_relation', payload: { relationId: l.sid } }, () => {
          store.caption('One proposal', `Removing “${l.a.label} ${l.label} ${l.b.label}” is waiting for your approval.`);
          renderAdmin();
        });
    },
    true,
  );
}

// ------------------------------------------------------------ companies

/**
 * Confirms removing a company, naming what goes from `POST /deletion-impact` (concepts, relations
 * with cross-company ones counted, attributes) in the style of concept deletion; the confirmation
 * proposes the removal. The home company is never offered.
 */
export function removeCompanyDialog(c: Company): Promise<void> {
  const sid = c.sid;
  if (!sid) return Promise.resolve();
  return attempt(() => api.deletionImpact({ companyId: sid, wholeCompany: true })).then((impact) => {
    if (!impact) return;
    confirmDialog(
      `Remove ${c.name}?`,
      impactText(impact, true),
      'Propose removal',
      () =>
        attemptThen(
          () => api.proposeRemoveCompany(sid),
          () => {
            store.toast2('Proposed', `removal of ${c.name} · approve it on the canvas`);
            renderAdmin();
          },
        ),
      true,
    );
  });
}

// ------------------------------------------------------------ domains, moves, bulk deletion

/** Proposes moving a concept to another domain product, chosen from the tenant's domains. */
export function moveDialog(n: Node): void {
  const sid = n.sid;
  const current = n.domain?.key ?? null;
  const options = store.ui.domains.filter((d) => d.key !== current);
  if (!sid || !options.length) return;
  store.openDialog({
    title: `Move ${n.label}`,
    sub: `from ${n.domain ? n.domain.name : 'the company'} to another domain product`,
    small: true,
    body: (
      <div className="form" style={{ gridTemplateColumns: '90px 1fr' }}>
        <label>Domain</label>
        <select id="mvDomain">
          {options.map((d) => (
            <option key={d.key} value={d.key}>
              {d.name}
            </option>
          ))}
        </select>
        <label></label>
        <small style={{ color: 'var(--ink-3)' }}>Its children and relations stay as they are. This proposes a change for approval.</small>
      </div>
    ),
    buttons: [
      { label: 'Cancel' },
      {
        label: 'Propose move',
        cls: 'primary',
        onClick: (bk) => {
          const key = bk.querySelector<HTMLSelectElement>('#mvDomain')?.value;
          const target = options.find((d) => d.key === key);
          if (!target) return;
          return attemptThen(
            () => api.proposeMoveConcept(sid, target.key),
            () => {
              store.toast2('Proposed', `move of ${n.label} to ${target.name}`);
              renderAdmin();
            },
          );
        },
      },
    ],
  });
}

/** A colour for a new domain: the first of the reference palette no domain uses, else the neutral. */
function freshColour(): string {
  const used = new Set(store.ui.domains.map((d) => d.color.toLowerCase()));
  return PALETTE.find((c) => !used.has(c.toLowerCase())) || NEUTRAL;
}

/** The name, owner and colour fields shared by the new-domain and edit-domain dialogs, with the Appearance colour input. */
function domainForm(d: { name: string; owner: string; color: string } | null) {
  return (
    <div className="form" style={{ gridTemplateColumns: '90px 1fr' }}>
      <label>Name</label>
      <input id="dmName" defaultValue={d ? d.name : ''} maxLength={60} placeholder="e.g. Sustainability" />
      <label>Owner</label>
      <input id="dmOwner" defaultValue={d ? d.owner : ''} maxLength={60} placeholder="e.g. Facilities" />
      <label>Colour</label>
      <label className="col">
        <input type="color" id="dmColor" defaultValue={d ? d.color : freshColour()} data-col="__domain" />
        <span>
          <b>Domain colour</b>
          <small>the same in every company</small>
        </span>
      </label>
    </div>
  );
}

function readDomainForm(bk: HTMLDivElement): DomainInput {
  return {
    name: (bk.querySelector<HTMLInputElement>('#dmName')?.value || '').trim(),
    owner: (bk.querySelector<HTMLInputElement>('#dmOwner')?.value || '').trim(),
    color: (bk.querySelector<HTMLInputElement>('#dmColor')?.value || '').toLowerCase(),
  };
}

/** Proposes a new tenant domain: name, owner and colour, available to every company once approved. */
export function newDomainDialog(): void {
  store.openDialog({
    title: 'New domain',
    sub: 'a domain product for every company, once approved',
    small: true,
    body: domainForm(null),
    buttons: [
      { label: 'Cancel' },
      {
        label: 'Propose domain',
        cls: 'primary',
        onClick: (bk) => {
          const input = readDomainForm(bk);
          if (!input.name) {
            bk.querySelector<HTMLInputElement>('#dmName')?.focus();
            return false;
          }
          return attemptThen(
            () => api.proposeCreateDomain(input),
            () => {
              store.toast2('Proposed', `new domain ${input.name} · approve it on the canvas`);
              renderAdmin();
            },
          );
        },
      },
    ],
  });
}

/** Proposes renaming, recolouring or re-owning a tenant domain; only what changed is sent. */
export function editDomainDialog(d: TenantDomain): void {
  store.openDialog({
    title: `Edit ${d.name}`,
    sub: 'the change applies in every company once approved',
    small: true,
    body: domainForm(d),
    buttons: [
      { label: 'Cancel' },
      {
        label: 'Propose change',
        cls: 'primary',
        onClick: (bk) => {
          const input = readDomainForm(bk);
          const patch: DomainPatch = {};
          if (input.name && input.name !== d.name) patch.name = input.name;
          if ((input.owner ?? '') !== d.owner) patch.owner = input.owner;
          if (input.color && input.color !== d.color.toLowerCase()) patch.color = input.color;
          if (!Object.keys(patch).length) {
            bk.querySelector<HTMLInputElement>('#dmName')?.focus();
            return false;
          }
          return attemptThen(
            () => api.proposeEditDomain(d.key, patch),
            () => {
              store.toast2('Proposed', `change of ${d.name} · approve it on the canvas`);
              renderAdmin();
            },
          );
        },
      },
    ],
  });
}

/** Confirms deleting one company's domain product with its concepts, naming what goes from the deletion impact. */
export function deleteDomainDialog(d: Domain): Promise<void> {
  const sid = d.sid,
    companyId = d.company.sid;
  if (!sid || !companyId) return Promise.resolve();
  return attempt(() => api.deletionImpact({ companyId, domainProductIds: [sid] })).then((impact) => {
    if (!impact) return;
    confirmDialog(
      `Delete ${d.name} of ${d.company.name}?`,
      impactText(impact, false),
      'Propose deletion',
      () =>
        attemptThen(
          () => api.proposeDeleteDomain(sid),
          () => {
            store.toast2('Proposed', `deletion of ${d.name} · approve it on the canvas`);
            renderAdmin();
          },
        ),
      true,
    );
  });
}

/** `3 concepts and 1 domain product`. */
export function bulkWhat(concepts: number, products: number): string {
  return [concepts ? plural(concepts, 'concept') : '', products ? plural(products, 'domain product') : ''].filter(Boolean).join(' and ');
}

/**
 * Confirms deleting several concepts and/or domain products of one company in one proposal,
 * naming what goes from the deletion impact. Refuses more than the API takes at once.
 */
export function bulkDeleteDialog(company: Company, concepts: Node[], products: Domain[]): Promise<void> {
  const companyId = company.sid;
  const conceptIds = concepts.map((n) => n.sid).filter((x): x is string => !!x);
  const productIds = products.map((d) => d.sid).filter((x): x is string => !!x);
  if (!companyId || (!conceptIds.length && !productIds.length)) return Promise.resolve();
  if (conceptIds.length > BULK_CONCEPTS || productIds.length > BULK_PRODUCTS) {
    store.toast2('Too many', `at most ${BULK_CONCEPTS} concepts and ${BULK_PRODUCTS} domain products at once`);
    return Promise.resolve();
  }
  const what = bulkWhat(conceptIds.length, productIds.length);
  return attempt(() => api.deletionImpact({ companyId, conceptIds, domainProductIds: productIds })).then((impact: DeletionImpact | null) => {
    if (!impact) return;
    confirmDialog(
      `Delete ${what}?`,
      impactText(impact, false),
      'Propose deletion',
      () =>
        attemptThen(
          () => api.proposeBulkDelete({ companyId, conceptIds, domainProductIds: productIds }),
          () => {
            store.toast2('Proposed', `deletion of ${what} · approve it on the canvas`);
            store.clearSelection();
            renderAdmin();
          },
        ),
      true,
    );
  });
}

/** The canvas selection as one bulk deletion; a selection across companies is explained, not sent. */
export function bulkDeleteSelection(): Promise<void> {
  const cells = [...store.s.selected];
  const companies = [...new Set(cells.map((n) => n.company))];
  if (!cells.length) return Promise.resolve();
  if (companies.length > 1 || !companies[0]) {
    store.toast2('One company at a time', 'a bulk deletion covers the cells of one company');
    return Promise.resolve();
  }
  return bulkDeleteDialog(companies[0], cells, []);
}
