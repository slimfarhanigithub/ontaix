import { api } from '../api/client';
import type { Envelope } from '../api/events';
import { ApiError, type Proposal, type TenantDomain } from '../api/types';
import { DOMAIN_R, DOMAIN_TEMPLATES, TEMPLATE_COUNT } from '../canvas/constants';
import { addCompany, addNode, domainCentre, domainOf } from '../canvas/state';
import type { Company } from '../canvas/types';
import { store } from './store';

const refusal = (status: number, code: string) => new ApiError(status, { title: code, status, code, detail: `${code} detail` });

const pending = (extra: Partial<Proposal> = {}): Proposal =>
  ({
    id: 'p1',
    type: 'concept',
    state: 'pending',
    title: 'Plant',
    color: '#3fb8a9',
    deps: [],
    ready: true,
    html: '<b>Plant</b>',
    relationIds: [],
    bindingIds: [],
    proposer: { kind: 'user' },
    origin: 'text',
    originDetail: null,
    approvals: [],
    createdAt: '2026-09-30T09:00:00Z',
    revision: 2,
    conceptId: 'c-plant',
    artefacts: { concepts: [{ id: 'c-plant', label: 'Plant' } as never], relations: [{ id: 'r-plant', label: 'operates' } as never] },
    ...extra,
  }) as Proposal;

function reset(): Company {
  const s = store.s;
  s.nodes.length = 0;
  s.links.length = 0;
  s.companies.length = 0;
  s.DOMAINS = [];
  s.selected.clear();
  s.stickyFocus = null;
  s.focusSet = null;
  store.ui.domains = DOMAIN_TEMPLATES.map((t, position) => ({ key: t.key, name: t.name, owner: t.owner, color: t.color, defaultColor: t.color, template: true, position, revision: 0 }));
  store.ui.appearance = { theme: 'dark', colors: {}, accent: '#3fb8a9', source: '#d6bd8a', defaults: { colors: {}, accent: '#3fb8a9', source: '#d6bd8a' } };
  const c = addCompany(s, 'Northwind Industries', '');
  c.sid = 'co-1';
  return c;
}

const envelope = (type: Envelope['type'], payload: Record<string, unknown>): Envelope => ({
  id: 'e1',
  type,
  occurredAt: '2026-09-30T09:00:00Z',
  tenantId: 't',
  sequence: 1,
  actor: { kind: 'user' },
  bulk: false,
  payload,
});

describe('approving at the revision the panel shows', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    store.ui.toasts = [];
    store.ui.proposals = [];
  });

  it('always sends expectedRevision', async () => {
    const approve = vi.spyOn(api, 'approve').mockResolvedValue({} as never);
    await store.approve(pending({ revision: 2 }));
    await store.approve(pending({ revision: undefined }));
    expect(approve.mock.calls).toEqual([
      ['p1', 2],
      ['p1', 0],
    ]);
  });

  it('a 409 proposal_changed shows the refusal toast and re-reads the panel instead of reloading the scene', async () => {
    vi.spyOn(api, 'approve').mockRejectedValue(refusal(409, 'proposal_changed'));
    const reload = vi.spyOn(store, 'reloadScene').mockResolvedValue();
    const fresh = pending({ revision: 3, title: 'Site' });
    vi.spyOn(api, 'listProposals').mockResolvedValue({ items: [fresh], page: 1, pageSize: 1, total: 1 });

    await store.approve(pending({ revision: 2 }));

    expect(reload).not.toHaveBeenCalled();
    expect(store.ui.toasts.map((t) => [t.strong, t.text])).toEqual([['Refused', 'proposal_changed detail']]);
    expect(store.ui.proposals.map((p) => [p.title, p.revision])).toEqual([['Site', 3]]);
  });
});

describe('editing a pending draft in place', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    store.ui.toasts = [];
    store.ui.proposals = [];
  });

  it('sends the revision the editor saw with the changed fields, and replaces the panel item', async () => {
    reset();
    const p = pending({ revision: 2 });
    store.ui.proposals = [pending({ id: 'p0', title: 'Other' }), p];
    const edit = vi.spyOn(api, 'editProposal').mockResolvedValue(pending({ revision: 3, title: 'Site', html: '<b>Site</b>' }));

    expect(await store.editProposal(p, { label: 'Site' })).toBe(true);

    expect(edit).toHaveBeenCalledWith('p1', { revision: 2, label: 'Site' });
    expect(store.ui.proposals.map((q) => [q.id, q.title, q.revision])).toEqual([
      ['p0', 'Other', 2],
      ['p1', 'Site', 3],
    ]);
  });

  it('a 409 proposal_changed toasts and brings the panel to the newer text; a duplicate label is the Already there caption', async () => {
    store.ui.proposals = [pending({ revision: 2 })];
    vi.spyOn(api, 'editProposal').mockRejectedValueOnce(refusal(409, 'proposal_changed')).mockRejectedValueOnce(refusal(409, 'duplicate_label'));
    vi.spyOn(api, 'listProposals').mockResolvedValue({ items: [pending({ revision: 3, title: 'Works' })], page: 1, pageSize: 1, total: 1 });

    expect(await store.editProposal(pending({ revision: 2 }), { label: 'Site' })).toBe(false);
    expect(store.ui.toasts.map((t) => [t.strong, t.text])).toEqual([['Refused', 'proposal_changed detail']]);
    expect(store.ui.proposals.map((p) => p.title)).toEqual(['Works']);

    expect(await store.editProposal(pending({ revision: 3 }), { label: 'Works' })).toBe(false);
    expect(store.ui.caption.kicker).toBe('Already there');
  });
});

describe('live events of editing and domains', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    store.ui.proposals = [];
  });

  it('proposal.changed replaces the panel item and relabels the pending cell and its line', () => {
    const c = reset();
    const n = addNode(store.s, { label: 'Plant', kind: 'concept', company: c, domain: domainOf(store.s, 'production', c), sid: 'c-plant', pending: true });
    store.ui.proposals = [pending({ revision: 0 })];
    vi.spyOn(api, 'listProposals').mockResolvedValue({ items: [pending({ revision: 1, title: 'Site' })], page: 1, pageSize: 1, total: 1 });
    const next = pending({ revision: 1, title: 'Site', artefacts: { concepts: [{ id: 'c-plant', label: 'Site' } as never], relations: [] } });

    store.handleEvent(envelope('proposal.changed', { proposal: next, artefacts: next.artefacts, cascaded: [] }));

    expect(store.ui.proposals.map((p) => [p.title, p.revision])).toEqual([['Site', 1]]);
    expect(n.label).toBe('Site');
  });

  it('domain.changed gives every company the domain with its colour and position, and renames a template everywhere', () => {
    const a = reset();
    const b = addCompany(store.s, 'Aurora Valves', '');
    const created: TenantDomain = { key: 'sustainability', name: 'Sustainability', owner: 'Facilities', color: '#112233', defaultColor: '#112233', template: false, position: 9, revision: 0 };

    store.handleEvent(envelope('domain.changed', { domain: created, created: true }));

    expect(store.ui.domains.map((d) => d.key)).toEqual([...DOMAIN_TEMPLATES.map((t) => t.key), 'sustainability']);
    for (const c of [a, b]) {
      const d = c.domains.find((x) => x.key === 'sustainability');
      expect(d).toMatchObject({ name: 'Sustainability', owner: 'Facilities', color: '#112233', position: 9, hidden: false, sid: null });
      expect(c.domains).toHaveLength(10);
    }
    expect(store.s.DOMAINS).toHaveLength(20);

    const plant = addNode(store.s, { label: 'Plant', kind: 'concept', company: a, domain: domainOf(store.s, 'production', a), sid: 'c-plant', color: '#3fb8a9' });
    store.handleEvent(
      envelope('domain.changed', {
        domain: { key: 'production', name: 'Manufacturing', owner: 'Works', color: '#abcdef', defaultColor: '#3fb8a9', template: true, position: 0, revision: 1 },
        created: false,
      }),
    );
    expect(a.domains[0]).toMatchObject({ key: 'production', name: 'Manufacturing', owner: 'Works', color: '#abcdef' });
    expect(b.domains[0].name).toBe('Manufacturing');
    expect(plant.color).toBe('#abcdef');
    expect(plant.finalColor).toBe('#abcdef');
  });
});

describe('custom domain placement', () => {
  it('keeps the nine templates on the reference ring and puts custom domains between them, then on outer rings', () => {
    const c = reset();
    for (const [i, d] of c.domains.entries()) {
      const a = -Math.PI / 2 + (i * 2 * Math.PI) / TEMPLATE_COUNT;
      expect(domainCentre(d)).toEqual([c.x + Math.cos(a) * DOMAIN_R, c.y + Math.sin(a) * DOMAIN_R]);
    }
    store.handleEvent(envelope('domain.changed', { domain: { key: 'x9', name: 'X9', owner: '', color: '#112233', defaultColor: '#112233', template: false, position: 9, revision: 0 }, created: true }));
    store.handleEvent(envelope('domain.changed', { domain: { key: 'x18', name: 'X18', owner: '', color: '#112233', defaultColor: '#112233', template: false, position: 18, revision: 0 }, created: true }));
    const half = -Math.PI / 2 + (0.5 * 2 * Math.PI) / TEMPLATE_COUNT;
    expect(domainCentre(c.domains[9])).toEqual([c.x + Math.cos(half) * DOMAIN_R, c.y + Math.sin(half) * DOMAIN_R]);
    expect(domainCentre(c.domains[10])).toEqual([c.x + Math.cos(half) * (DOMAIN_R + 300), c.y + Math.sin(half) * (DOMAIN_R + 300)]);
    // The templates did not move.
    const a0 = -Math.PI / 2;
    expect(domainCentre(c.domains[0])).toEqual([c.x + Math.cos(a0) * DOMAIN_R, c.y + Math.sin(a0) * DOMAIN_R]);
  });
});

describe('canvas selection', () => {
  it('toggles approved cells in and out, shows them as the sticky focus set, and clears on Escape', () => {
    const c = reset();
    const plant = addNode(store.s, { label: 'Plant', kind: 'concept', company: c, sid: 'c-plant' });
    const line = addNode(store.s, { label: 'Line', kind: 'concept', company: c, sid: 'c-line' });
    const draft = addNode(store.s, { label: 'Maybe', kind: 'concept', company: c, sid: 'c-maybe', pending: true });
    store.toggleSelected(plant);
    store.toggleSelected(line);
    store.toggleSelected(draft);
    if (c.root) store.toggleSelected(c.root);
    expect([...store.s.selected].map((n) => n.label)).toEqual(['Plant', 'Line']);
    expect(store.s.stickyFocus).toEqual(new Set([plant, line]));
    expect(store.s.focusSet).toBe(store.s.stickyFocus);
    store.toggleSelected(plant);
    expect([...store.s.selected].map((n) => n.label)).toEqual(['Line']);
    store.escape();
    expect(store.s.selected.size).toBe(0);
    expect(store.s.stickyFocus).toBeNull();
  });

  it('drops cells that left the model', () => {
    const c = reset();
    const plant = addNode(store.s, { label: 'Plant', kind: 'concept', company: c, sid: 'c-plant' });
    store.toggleSelected(plant);
    plant.dying = { start: 0 };
    store.pruneSelection();
    expect(store.s.selected.size).toBe(0);
  });
});
