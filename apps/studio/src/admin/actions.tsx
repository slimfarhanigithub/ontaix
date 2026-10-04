/**
 * What the admin portal's buttons do, and the dialogs they open: settings, the typed `disable`
 * confirmation, rename, bind and unbind, source enable, disable and removal, company removal,
 * group edit, members and roles, the role-to-groups list, the scope choice and the agent
 * registry. Behaviour and copy from reference/ontaix-studio-reference.html lines 947-1053.
 * Ontology changes are proposals; settings, directory and source-state changes are immediate.
 * The ontology-editing dialogs (move to domain, company removal named from the deletion impact,
 * domain creation, edit and deletion, bulk deletion) are owner additions in the same markup.
 */
import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react';

import { api } from '../api/client';
import type { DeletionImpact, DomainInput, DomainPatch, Group, ProposalDraft, Scope, TenantDomain, User } from '../api/types';
import { DOMAIN_TEMPLATES, NEUTRAL, PALETTE } from '../canvas/constants';
import type { Company, Domain, Link, Node } from '../canvas/types';
import { title } from '../nl/parser';
import { BusyButton, useBusyAction } from '../shell/busy';
import { DialogFrame } from '../shell/Dialog';
import { store } from '../store/store';
import { attempt, directory, failed, fetchAll, invalidateDirectory } from './adminData';
import { conceptDeletion, deletionText, impactText } from './conceptDeletion';

/** Most concepts and domain products one bulk deletion may name. */
export const BULK_CONCEPTS = 200;
export const BULK_PRODUCTS = 20;
import { isDisableConfirmed } from './confirmText';
import { List, type Column } from './List';
import { en } from './listModel';
import { roleLabel, roleName, ROLE_NAMES } from './roles';
import { Tg, type SettingKey } from './Toggle';

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

/** Re-reads the directory and redraws the portal from scratch. */
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

export function changeRefresh(value: string): void {
  void attempt(() => api.patchSettings({ refresh: value as '5 min' | '15 min' | '1 h' | 'daily' })).then((next) => {
    if (next) store.ui.settings = next;
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
        without a proposal. Each company keeps its own concepts, relations and bindings.
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

/** Applies a colour at once and saves it after the picker settles. */
export function changeColour(key: string, value: string): void {
  const ap = store.ui.appearance;
  if (!ap) return;
  const patch = key === '__accent' ? { accent: value } : key === '__source' ? { source: value } : { colors: { [key]: value } };
  store.ui.appearance = {
    ...ap,
    accent: key === '__accent' ? value : ap.accent,
    source: key === '__source' ? value : ap.source,
    colors: key.startsWith('__') ? ap.colors : { ...ap.colors, [key]: value },
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

// ------------------------------------------------------------ entities, relations, bindings

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

export function bindDialog(n: Node): void {
  const srcs = store.s.nodes.filter((x) => x.kind === 'source' && x.company === n.company && !x.pending && !x.dying);
  if (!srcs.length) {
    store.toast2('No source', `add a data source for ${n.company?.name} first`);
    return;
  }
  store.openDialog({
    title: `Bind ${n.label}`,
    small: true,
    body: (
      <div className="form" style={{ gridTemplateColumns: '90px 1fr' }}>
        <label>Source</label>
        <select id="bdSrc">
          {srcs.map((x) => (
            <option key={x.id} value={x.id}>{`${x.label} · ${x.sub}`}</option>
          ))}
        </select>
        <label></label>
        <small style={{ color: 'var(--ink-3)' }}>The binding is proposed; attributes found in the schema follow as their own proposals.</small>
      </div>
    ),
    buttons: [
      { label: 'Cancel' },
      {
        label: 'Propose binding',
        cls: 'primary',
        onClick: (bk) => {
          const id = bk.querySelector<HTMLSelectElement>('#bdSrc')?.value;
          const src = srcs.find((x) => String(x.id) === id);
          if (!src || !src.sid || !n.sid) return;
          return proposeThen({ type: 'bind', sourceId: src.sid, conceptIds: [n.sid] }, () => {
            store.toast2('Proposed', `${n.label} bound to ${src.label}`);
            renderAdmin();
          });
        },
      },
    ],
  });
}

export function unbindDialog(n: Node, source: string, attrs: number): void {
  confirmDialog(
    `Unbind ${n.label} from ${source}?`,
    `This proposes a change for approval. ${n.label} keeps its ${attrs} approved attributes as declared; record count and freshness disappear.`,
    'Propose unbinding',
    () => {
      const link = store.s.links.find((l) => l.kind === 'bind' && l.b === n && !l.pending);
      const sid = link?.sid;
      if (sid)
        return attemptThen(
          () => api.proposeUnbind(sid),
          () => {
            store.toast2('Proposed', `unbinding of ${n.label}`);
            renderAdmin();
          },
        );
    },
    true,
  );
}

// ------------------------------------------------------------ sources and companies

export function toggleSource(n: Node): Promise<void> {
  const sid = n.sid;
  if (!sid) return Promise.resolve();
  const doIt = () => {
    const off = !n.disabled;
    return attempt(() => (off ? api.disableSource(sid) : api.enableSource(sid))).then((src) => {
      if (!src) return;
      n.disabled = src.disabled;
      store.toast2(src.disabled ? 'Disabled' : 'Enabled', n.label);
      renderAdmin();
    });
  };
  if (n.disabled) return doIt();
  const fed = store.s.links.filter((l) => l.kind === 'bind' && l.a === n).length;
  confirmDialog(
    `Disable ${n.label}?`,
    <>
      {`Syncing stops. The ${plural(fed, 'concept')} it feeds keep their attributes; counts and freshness are marked `}
      <b>paused</b> until you enable it again.
    </>,
    'Disable',
    doIt,
  );
  return Promise.resolve();
}

export function removeSourceDialog(n: Node): void {
  const fed = store.s.links.filter((l) => l.kind === 'bind' && l.a === n).map((l) => l.b.label);
  confirmDialog(
    `Delete ${n.label}?`,
    fed.length ? (
      <>
        This proposes a change for approval. The following concepts would lose their binding: <b>{fed.join(', ')}</b>. They keep their attributes as
        declared.
      </>
    ) : (
      'This proposes a change for approval. Nothing is bound to it.'
    ),
    'Propose deletion',
    () => {
      const sid = n.sid;
      if (sid)
        return attemptThen(
          () => api.proposeRemoveSource(sid),
          () => {
            store.caption('One proposal', `Removing ${n.label} is waiting for approval.`);
            store.toast2('Proposed', `deletion of ${n.label} · approve it on the canvas`);
            renderAdmin();
          },
        );
    },
    true,
  );
}

/**
 * Confirms removing a company, naming what goes from `POST /deletion-impact` (concepts, relations
 * with cross-company ones counted, sources, bindings, attributes) in the style of concept
 * deletion; the confirmation proposes the removal. The home company is never offered.
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
        <small style={{ color: 'var(--ink-3)' }}>Its children, relations and bindings stay as they are. This proposes a change for approval.</small>
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

// ------------------------------------------------------------ groups, roles, agents

/** Tenant, each company, each domain product family: the reference's `SCOPES()`. */
export function localScopes(): Scope[] {
  return [
    { kind: 'tenant', companyId: null, domainKey: null, label: 'Tenant' },
    ...store.s.companies.map((c) => ({ kind: 'company' as const, companyId: c.sid, domainKey: null, label: c.name })),
    ...DOMAIN_TEMPLATES.map((t) => ({ kind: 'domain' as const, companyId: null, domainKey: t.key, label: t.name })),
  ];
}

export function groupEdit(g: Group | null): void {
  store.openDialog({
    title: g ? `Edit ${g.name}` : 'Create a group',
    small: true,
    body: (
      <div className="form" style={{ gridTemplateColumns: '100px 1fr' }}>
        <label>Name</label>
        <input id="gName" defaultValue={g ? g.name : ''} placeholder="e.g. Quality · owners" />
        <label>Description</label>
        <input id="gDesc" defaultValue={g ? g.description : ''} placeholder="what this group is for" />
      </div>
    ),
    buttons: [
      { label: 'Cancel' },
      {
        label: g ? 'Save' : 'Create',
        cls: 'primary',
        onClick: (bk) => {
          const nameInput = bk.querySelector<HTMLInputElement>('#gName');
          const name = (nameInput?.value || '').trim();
          if (!name) {
            nameInput?.focus();
            return false;
          }
          const description = (bk.querySelector<HTMLInputElement>('#gDesc')?.value || '').trim();
          if (g)
            return attempt(() => api.updateGroup(g.id, { name, description })).then((r) => {
              if (!r) return;
              store.toast2('Saved', name);
              renderAdmin();
            });
          return attempt(() => api.createGroup({ name, description })).then((ng) => {
            if (!ng) return;
            store.toast2('Created', name);
            renderAdmin();
            setTimeout(() => groupMembers(ng), 150);
          });
        },
      },
    ],
  });
}

interface MemberRow extends Record<string, unknown> {
  id: string;
  name: string;
  email: string;
  dept: string;
  company: string;
  on: boolean;
}

export function groupMembers(g: Group): void {
  store.openDialog({ render: (close) => <MembersDialog g={g} close={close} /> });
}

function memberRows(users: User[], g: Group): MemberRow[] {
  return users.map((u) => ({
    id: u.id,
    name: u.name,
    email: u.email,
    dept: u.department || '',
    company: u.companyName || '',
    on: u.groups.some((x) => x.id === g.id),
  }));
}

function MembersDialog({ g, close }: { g: Group; close: () => void }) {
  const [rows, setRows] = useState<MemberRow[]>(() => memberRows(directory.users, g));
  useEffect(() => {
    if (directory.users.length) return;
    void fetchAll((p) => api.listUsers(p))
      .then((users) => setRows(memberRows(users, g)))
      .catch((err: unknown) => failed(err, 'Unavailable'));
  }, [g]);
  const toggle = (r: MemberRow) => {
    const on = !r.on;
    return attempt(() => (on ? api.addGroupMember(g.id, r.id) : api.removeGroupMember(g.id, r.id))).then((res) => {
      if (res === null) return;
      setRows((cur) => cur.map((x) => (x.id === r.id ? { ...x, on } : x)));
    });
  };
  const columns: Column[] = [
    { label: 'User', key: 'name' },
    { label: 'Email', key: 'email' },
    { label: 'Department', key: 'dept' },
    { label: 'Company', key: 'company' },
    { label: 'Member', w: '100px' },
  ];
  return (
    <ListDialogFrame
      title={`Members · ${g.name}`}
      sub="add or remove users · the directory is Ontaix’s own"
      close={close}
      buttons={[{ label: 'Done', cls: 'primary', onClick: () => renderAdmin() }]}
    >
      <List
        columns={columns}
        rows={rows}
        rowKey={(r) => r.id}
        searchKeys={['name', 'email', 'dept', 'company']}
        filterKey="dept"
        pageSize={40}
        renderRow={(r) => (
          <>
            <td>
              <b>{r.name}</b>
            </td>
            <td className="wrap" style={{ color: 'var(--ink-2)' }}>{r.email}</td>
            <td>{r.dept}</td>
            <td>{r.company}</td>
            <td>
              <Tg on={r.on} data-fn="member" onClick={() => toggle(r)} />
            </td>
          </>
        )}
        footer={() => `${rows.filter((x) => x.on).length} members in the group`}
      />
    </ListDialogFrame>
  );
}

export function groupRoles(g: Group): void {
  store.openDialog({ render: (close) => <RolesDialog g={g} close={close} /> });
}

function RolesDialog({ g, close }: { g: Group; close: () => void }) {
  const [roles, setRoles] = useState(g.roles);
  const roleSel = useRef<HTMLSelectElement>(null);
  const scopeSel = useRef<HTMLSelectElement>(null);
  const scopes = localScopes();
  const add = () => {
    const role = roleSel.current?.value || ROLE_NAMES[0],
      label = scopeSel.current?.value || 'Tenant';
    const scope = scopes.find((x) => x.label === label);
    if (!scope || roles.some((r) => roleLabel(r.role) === role && r.scope.label === label)) return;
    return attempt(() => api.addGroupRole(g.id, { role: roleName(role), scope })).then((a) => {
      if (a) setRoles((cur) => [...cur, a]);
    });
  };
  const remove = (id: string) => {
    void attempt(() => api.removeGroupRole(g.id, id)).then((res) => {
      if (res !== null) setRoles((cur) => cur.filter((r) => r.id !== id));
    });
  };
  return (
    <DialogFrame
      title={`Roles · ${g.name}`}
      sub="a role plus the scope it applies to"
      onClose={close}
      footer={
        <button
          className="btn primary"
          data-i={0}
          onClick={() => {
            close();
            store.toast2('Saved', `roles of ${g.name}`);
            renderAdmin();
          }}
        >
          Done
        </button>
      }
    >
      <div className="chips2" id="grRoles">
        {roles.length ? (
          roles.map((r, i) => (
            <span key={r.id}>
              {`${roleLabel(r.role)} · ${r.scope.label}`}
              <b data-i={i} title="Remove" onClick={() => remove(r.id)}>
                ×
              </b>
            </span>
          ))
        ) : (
          <small style={{ color: 'var(--ink-3)' }}>No role yet.</small>
        )}
      </div>
      <div className="form" style={{ marginTop: '14px', gridTemplateColumns: '80px 1fr 1fr auto' }}>
        <label>Add</label>
        <select id="grRole" ref={roleSel}>
          {ROLE_NAMES.map((r) => (
            <option key={r}>{r}</option>
          ))}
        </select>
        <select id="grScope" ref={scopeSel}>
          {scopes.map((x) => (
            <option key={`${x.kind}:${x.label}`}>{x.label}</option>
          ))}
        </select>
        <BusyButton className="btn" id="grAdd" onClick={add}>
          Add
        </BusyButton>
      </div>
      <p style={{ margin: '12px 0 0', color: 'var(--ink-3)', fontSize: '12px' }}>
        Owner and Governor on the same scope is what certification needs. Administrator only applies at Tenant scope.
      </p>
    </DialogFrame>
  );
}

export function deleteGroupDialog(g: Group): void {
  const nroles = g.roles.length;
  confirmDialog(
    `Delete “${g.name}”?`,
    `Its ${plural(g.memberCount, 'member')} lose the ${plural(nroles, 'role assignment')} it carries. Users themselves are not deleted.`,
    'Delete group',
    () =>
      attempt(() => api.deleteGroup(g.id)).then((res) => {
        if (res === null) return;
        store.toast2('Deleted', g.name);
        renderAdmin();
      }),
    true,
  );
}

interface HoldRow extends Record<string, unknown> {
  id: string;
  g: Group;
  name: string;
  desc: string;
  members: number;
  scopes: string;
  on: boolean;
}

/** Which groups hold a role, and on which scope. */
export function roleGroups(role: string): void {
  store.openDialog({ render: (close) => <RoleGroupsDialog role={role} close={close} /> });
}

const holdRow = (g: Group, role: string): HoldRow => {
  const mine = g.roles.filter((r) => roleLabel(r.role) === role);
  return {
    id: g.id,
    g,
    name: g.name,
    desc: g.description,
    members: g.memberCount,
    scopes: mine.map((r) => r.scope.label).join(', ') || '—',
    on: mine.length > 0,
  };
};

function RoleGroupsDialog({ role, close }: { role: string; close: () => void }) {
  const [rows, setRows] = useState<HoldRow[]>(() => directory.groups.map((g) => holdRow(g, role)));
  const replace = (g: Group) => setRows((cur) => cur.map((x) => (x.id === g.id ? holdRow(g, role) : x)));
  const hold = (r: HoldRow) => {
    if (r.on) {
      const drop = r.g.roles.filter((a) => roleLabel(a.role) === role);
      return Promise.allSettled(drop.map((a) => api.removeGroupRole(r.g.id, a.id))).then((results) => {
        const removed = drop.filter((_, i) => results[i].status === 'fulfilled');
        replace({ ...r.g, roles: r.g.roles.filter((a) => !removed.includes(a)) });
        const refusal = results.find((x): x is PromiseRejectedResult => x.status === 'rejected');
        if (refusal) failed(refusal.reason);
      });
    }
    const scopes = localScopes();
    store.openDialog({
      title: `${role} on which scope?`,
      small: true,
      body: (
        <div className="form" style={{ gridTemplateColumns: '80px 1fr' }}>
          <label>Scope</label>
          <select id="rsScope">
            {scopes.map((x) => (
              <option key={`${x.kind}:${x.label}`}>{x.label}</option>
            ))}
          </select>
        </div>
      ),
      buttons: [
        { label: 'Cancel' },
        {
          label: 'Give role',
          cls: 'primary',
          onClick: (bk) => {
            const label = bk.querySelector<HTMLSelectElement>('#rsScope')?.value;
            const scope = scopes.find((x) => x.label === label);
            if (!scope) return;
            return attempt(() => api.addGroupRole(r.g.id, { role: roleName(role), scope })).then((a) => {
              if (a) replace({ ...r.g, roles: [...r.g.roles, a] });
            });
          },
        },
      ],
    });
  };
  const columns: Column[] = [
    { label: 'Group', key: 'name' },
    { label: 'Description', key: 'desc' },
    { label: 'Members', key: 'members', num: true },
    { label: 'Scope', key: 'scopes' },
    { label: 'Holds role', w: '100px' },
  ];
  return (
    <ListDialogFrame
      title={`${role} · groups`}
      sub="which Ontaix groups hold this role, and on which scope"
      close={close}
      buttons={[{ label: 'Done', cls: 'primary', onClick: () => renderAdmin() }]}
    >
      <List
        columns={columns}
        rows={rows}
        rowKey={(r) => r.id}
        searchKeys={['name', 'desc', 'scopes']}
        pageSize={40}
        renderRow={(r) => (
          <>
            <td>
              <b>{r.name}</b>
            </td>
            <td style={{ color: 'var(--ink-2)' }}>{r.desc}</td>
            <td className="num">{r.members}</td>
            <td>{r.scopes}</td>
            <td>
              <Tg on={r.on} data-fn="hold" onClick={() => hold(r)} />
            </td>
          </>
        )}
        footer={(l) => `${l.filter((x) => x.on).length} groups hold ${role}`}
      />
    </ListDialogFrame>
  );
}

interface AgentRow extends Record<string, unknown> {
  id: string;
  name: string;
  platform: string;
  domain: string;
  owner: string;
  reads: number;
  cost: number;
  on: boolean;
}

export function agentRegistry(): void {
  store.openDialog({ render: (close) => <RegistryDialog close={close} /> });
}

function RegistryDialog({ close }: { close: () => void }) {
  const [rows, setRows] = useState<AgentRow[]>([]);
  useEffect(() => {
    void fetchAll((p) => api.listAgents(p))
      .then((agents) =>
        setRows(
          agents.map((a) => ({
            id: a.id,
            name: a.name,
            platform: a.platform,
            domain: a.domainName || '—',
            owner: a.owner,
            reads: a.reads,
            cost: a.costEur,
            on: a.access,
          })),
        ),
      )
      .catch((err: unknown) => failed(err, 'Unavailable'));
  }, []);
  const toggle = (r: AgentRow) =>
    attempt(() => api.updateAgent(r.id, !r.on)).then((a) => {
      if (a) setRows((cur) => cur.map((x) => (x.id === r.id ? { ...x, on: a.access } : x)));
    });
  const columns: Column[] = [
    { label: 'Agent', key: 'name' },
    { label: 'Platform', key: 'platform' },
    { label: 'Domain product', key: 'domain' },
    { label: 'Owner', key: 'owner' },
    { label: 'Reads · month', key: 'reads', num: true },
    { label: 'Cost · month', key: 'cost', num: true },
    { label: 'Access', w: '100px' },
  ];
  return (
    <ListDialogFrame
      title="Agent registry"
      sub="every agent, from every platform, that can read this model through the gateway"
      close={close}
      buttons={[{ label: 'Close' }]}
    >
      <List
        columns={columns}
        rows={rows}
        rowKey={(r) => r.id}
        searchKeys={['name', 'platform', 'domain', 'owner']}
        filterKey="platform"
        pageSize={50}
        renderRow={(r) => (
          <>
            <td>
              <b>{r.name}</b>
            </td>
            <td>{r.platform}</td>
            <td>{r.domain}</td>
            <td>{r.owner}</td>
            <td className="num">{en(r.reads)}</td>
            <td className="num">{`€ ${en(r.cost)}`}</td>
            <td>
              <Tg on={r.on} data-fn="toggle" onClick={() => toggle(r)} />
            </td>
          </>
        )}
        footer={(l) => `${en(l.filter((x) => x.on).length)} with access · € ${en(l.reduce((a, x) => a + x.cost, 0))}`}
      />
    </ListDialogFrame>
  );
}

/** The large list dialog (`listDialog`): a list host in the body; the search box takes focus. */
function ListDialogFrame({
  title: heading,
  sub,
  close,
  buttons,
  children,
}: {
  title: string;
  sub: string;
  close: () => void;
  buttons: { label: string; cls?: string; onClick?: () => void }[];
  children: ReactNode;
}) {
  const back = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const t = setTimeout(() => back.current?.querySelector<HTMLInputElement>('.search')?.focus(), 40);
    return () => clearTimeout(t);
  }, []);
  return (
    <DialogFrame
      title={heading}
      sub={sub}
      large
      onClose={close}
      backRef={back}
      footer={buttons.map((b, i) => (
        <button
          key={i}
          className={`btn ${b.cls || ''}`}
          data-i={i}
          onClick={() => {
            b.onClick?.();
            close();
          }}
        >
          {b.label}
        </button>
      ))}
    >
      <div className="lst-host">{children}</div>
    </DialogFrame>
  );
}

