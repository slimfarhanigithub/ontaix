import { act, fireEvent, render } from '@testing-library/react';

import { api } from '../api/client';
import { ApiError, type Group, type Proposal, type TeachResult } from '../api/types';
import { groupEdit, toggleSource } from '../admin/actions';
import { Tg } from '../admin/Toggle';
import { addCompany, addNode, addSource, domainOf } from '../canvas/state';
import type { Company, Node } from '../canvas/types';
import { store } from '../store/store';
import { speechStream, teach } from '../teach/teach';
import { BUSY_DELAY_MS, BusyButton, useBusyAction } from './busy';
import { Dialog } from './Dialog';
import { Drawer } from './Drawer';
import { openExpandDialog } from './ExpandDialog';
import { Panel } from './Panel';
import { STATUS_MIN_MS, TeachStatus } from './TeachStatus';

/** A promise with its resolve and reject in hand. */
function deferred<T = void>() {
  let resolve!: (v: T) => void, reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const advance = (ms: number) => act(() => vi.advanceTimersByTime(ms));
const settle = () => act(async () => {});
const spinOf = (el: Element | null | undefined) => el?.querySelector(':scope > .spin') ?? null;

function model(): { c: Company; sales: Node } {
  const s = store.s;
  s.nodes.length = 0;
  s.links.length = 0;
  s.companies.length = 0;
  s.DOMAINS = [];
  const c = addCompany(s, 'Northwind Industries', '');
  c.sid = 'co-1';
  if (c.root) c.root.sid = 'root-1';
  const sales = addNode(s, { label: 'Sales', kind: 'concept', company: c, domain: domainOf(s, 'sales', c), parent: c.root ?? undefined, sid: 'c-sales' });
  return { c, sales };
}

const proposal: Proposal = {
  id: 'p-1',
  type: 'concept',
  state: 'pending',
  title: 'After-sales',
  heading: 'New concept',
  color: '#fff',
  deps: [],
  ready: true,
  html: '<b>After-sales</b>',
  why: '',
  relationIds: [],
  bindingIds: [],
} as unknown as Proposal;

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  store.ui.dialogs = [];
  store.ui.drawerNode = null;
  store.ui.proposals = [];
  store.ui.toasts = [];
  store.ui.expanding = null;
});

describe('BusyButton', () => {
  it('shows the spinner before the unchanged label only once the wait passes 250 ms, disabled and aria-busy', async () => {
    const d = deferred();
    const { container } = render(<BusyButton onClick={() => d.promise}>Approve</BusyButton>);
    const button = container.querySelector('button') as HTMLButtonElement;
    fireEvent.click(button);
    await advance(BUSY_DELAY_MS - 1);
    expect(spinOf(button)).toBeNull();
    expect(button.disabled).toBe(false);
    expect(button.getAttribute('aria-busy')).toBeNull();
    await advance(1);
    expect(button.firstElementChild?.className).toBe('spin');
    expect(button.textContent).toBe('Approve');
    expect(button.disabled).toBe(true);
    expect(button.getAttribute('aria-busy')).toBe('true');
    d.resolve();
    await settle();
    expect(spinOf(button)).toBeNull();
    expect(button.disabled).toBe(false);
    expect(button.getAttribute('aria-busy')).toBeNull();
  });

  it('never flashes for a call that settles within 250 ms', async () => {
    const d = deferred();
    const { container } = render(<BusyButton onClick={() => d.promise}>Reject</BusyButton>);
    const button = container.querySelector('button') as HTMLButtonElement;
    fireEvent.click(button);
    await advance(200);
    d.resolve();
    await settle();
    await advance(500);
    expect(spinOf(button)).toBeNull();
    expect(button.disabled).toBe(false);
  });

  it('clears on failure and hands the rejection back', async () => {
    const d = deferred();
    const caught: unknown[] = [];
    function Save() {
      const { shown, run } = useBusyAction();
      return (
        <button disabled={shown} onClick={() => run(() => d.promise)?.catch((e: unknown) => caught.push(e))}>
          {shown ? <span className="spin"></span> : null}
          Save
        </button>
      );
    }
    const { container } = render(<Save />);
    const button = container.querySelector('button') as HTMLButtonElement;
    fireEvent.click(button);
    await advance(BUSY_DELAY_MS);
    expect(spinOf(button)).not.toBeNull();
    d.reject(new Error('refused'));
    await settle();
    expect(spinOf(button)).toBeNull();
    expect(button.disabled).toBe(false);
    expect(caught).toHaveLength(1);
  });

  it('ignores clicks while the first one is pending', async () => {
    const d = deferred();
    const click = vi.fn(() => d.promise);
    const { container } = render(<BusyButton onClick={click}>Approve all</BusyButton>);
    const button = container.querySelector('button') as HTMLButtonElement;
    fireEvent.click(button);
    fireEvent.click(button);
    await advance(100);
    fireEvent.click(button);
    expect(click).toHaveBeenCalledTimes(1);
    d.resolve();
    await settle();
    fireEvent.click(button);
    expect(click).toHaveBeenCalledTimes(2);
    await settle();
  });

  it('does nothing visible for a synchronous click', async () => {
    const click = vi.fn();
    const { container } = render(<BusyButton onClick={click}>Open</BusyButton>);
    const button = container.querySelector('button') as HTMLButtonElement;
    fireEvent.click(button);
    fireEvent.click(button);
    await advance(500);
    expect(click).toHaveBeenCalledTimes(2);
    expect(spinOf(button)).toBeNull();
  });
});

describe('proposals panel', () => {
  it('Approve waits on the API with the spinner, and Approve all ignores a second click', async () => {
    const approve = deferred();
    vi.spyOn(api, 'approve').mockReturnValue(approve.promise as never);
    const all = deferred<{ caption: string }>();
    const approveAll = vi.spyOn(api, 'approveAll').mockReturnValue(all.promise as never);
    store.ui.proposals = [proposal];
    const { container } = render(<Panel />);
    const ok = container.querySelector('.prop .act button.ok') as HTMLButtonElement;
    fireEvent.click(ok);
    await advance(BUSY_DELAY_MS);
    expect(ok.firstElementChild?.className).toBe('spin');
    expect(ok.textContent).toBe('Approve');
    expect(ok.disabled).toBe(true);
    approve.resolve();
    await settle();
    expect(spinOf(ok)).toBeNull();

    const bulk = container.querySelector('#approveAll') as HTMLButtonElement;
    fireEvent.click(bulk);
    fireEvent.click(bulk);
    await advance(BUSY_DELAY_MS);
    expect(approveAll).toHaveBeenCalledTimes(1);
    expect(bulk.getAttribute('aria-busy')).toBe('true');
    all.resolve({ caption: 'done' });
    await settle();
    expect(bulk.getAttribute('aria-busy')).toBeNull();
  });
});

describe('drawer', () => {
  it('Delete asks, and the confirmation waits for the proposal before it closes', async () => {
    const { sales } = model();
    const sent = deferred();
    vi.spyOn(store, 'propose').mockReturnValue(sent.promise.then(() => proposal) as never);
    store.ui.drawerNode = sales;
    const drawer = render(<Drawer />);
    const dialogs = render(<Dialog />);
    act(() => fireEvent.click(drawer.container.querySelector('#drDelete') as HTMLButtonElement));
    const yes = dialogs.container.querySelector('.dlg .df .btn.danger') as HTMLButtonElement;
    expect(yes.textContent).toBe('Propose deletion');
    fireEvent.click(yes);
    await advance(BUSY_DELAY_MS);
    expect(yes.firstElementChild?.className).toBe('spin');
    expect(yes.disabled).toBe(true);
    expect(dialogs.container.querySelector('.dlg')).not.toBeNull();
    sent.resolve();
    await settle();
    expect(dialogs.container.querySelector('.dlg')).toBeNull();
  });

  it('Expand: the drawer button, the waiting line and Suggest spin while the model answers, then Propose spins', async () => {
    const { sales } = model();
    const answer = deferred<unknown>();
    vi.spyOn(api, 'expandConcept').mockReturnValue(answer.promise as never);
    const proposed = deferred<unknown>();
    vi.spyOn(api, 'proposeExpansion').mockReturnValue(proposed.promise as never);
    store.ui.drawerNode = sales;
    const drawer = render(<Drawer />);
    const dialogs = render(<Dialog />);
    act(() => openExpandDialog(sales));
    const suggest = dialogs.container.querySelector('.dlg .df .btn.primary') as HTMLButtonElement;
    fireEvent.click(suggest);
    await advance(BUSY_DELAY_MS - 1);
    expect(dialogs.container.querySelector('#exWait')).toBeNull();
    expect(spinOf(drawer.container.querySelector('#drExpand'))).toBeNull();
    await advance(1);
    const expand = drawer.container.querySelector('#drExpand') as HTMLButtonElement;
    expect(expand.firstElementChild?.className).toBe('spin');
    expect(expand.textContent).toBe('Expand');
    expect(expand.disabled).toBe(true);
    expect(suggest.firstElementChild?.className).toBe('spin');
    const wait = dialogs.container.querySelector('#exWait');
    expect(wait?.firstElementChild?.className).toBe('spin');
    expect(wait?.textContent).toBe('Expanding Sales…');
    expect(dialogs.container.querySelector('#exDepth')).toBeNull();

    answer.resolve({
      expansionId: 'x-1',
      expiresAt: '2026-09-29T13:00:00Z',
      conceptId: 'c-sales',
      llmOutcome: 'used',
      degraded: false,
      drafts: [{ type: 'concept', companyId: 'co-1', parentId: 'c-sales', label: 'After-sales', domainKey: 'sales', action: 'includes' }],
      notes: [{ confidence: 0.9, rationale: 'r', depth: 1, requires: [] }],
      skipped: [],
    });
    await settle();
    expect(spinOf(drawer.container.querySelector('#drExpand'))).toBeNull();
    expect((drawer.container.querySelector('#drExpand') as HTMLButtonElement).disabled).toBe(false);

    const propose = dialogs.container.querySelector('.dlg .df .btn.primary') as HTMLButtonElement;
    expect(propose.textContent).toBe('Propose 1');
    fireEvent.click(propose);
    await advance(BUSY_DELAY_MS);
    expect(propose.firstElementChild?.className).toBe('spin');
    expect(propose.textContent).toBe('Propose 1');
    expect(propose.disabled).toBe(true);
    proposed.resolve([]);
    await settle();
    expect(dialogs.container.querySelector('.dlg')).toBeNull();
  });
});

describe('admin', () => {
  it('the source toggle shows the spinner in the dot’s place while enabling', async () => {
    const { c } = model();
    const src = addSource(store.s, c, 'SAP ERP', 'ERP');
    src.sid = 'src-1';
    src.disabled = true;
    const enabled = deferred<unknown>();
    vi.spyOn(api, 'enableSource').mockReturnValue(enabled.promise as never);
    const { container } = render(<Tg on={false} onClick={() => toggleSource(src)} />);
    const tg = container.querySelector('.tg') as HTMLButtonElement;
    fireEvent.click(tg);
    await advance(BUSY_DELAY_MS);
    expect(tg.firstElementChild?.className).toBe('spin');
    expect(tg.querySelector('i')).toBeNull();
    expect(tg.textContent).toBe('Enable');
    expect(tg.disabled).toBe(true);
    enabled.resolve({ disabled: false });
    await settle();
    expect(spinOf(tg)).toBeNull();
    expect(tg.querySelector('i')).not.toBeNull();
  });

  it('Save on a group waits for the API, then closes; a refusal clears the spinner too', async () => {
    const g = { id: 'g-1', name: 'Quality', description: '', memberCount: 0, roles: [] } as unknown as Group;
    const saved = deferred<unknown>();
    vi.spyOn(api, 'updateGroup').mockReturnValue(saved.promise as never);
    const { container } = render(<Dialog />);
    act(() => groupEdit(g));
    const save = container.querySelector('.dlg .df .btn.primary') as HTMLButtonElement;
    expect(save.textContent).toBe('Save');
    fireEvent.click(save);
    await advance(BUSY_DELAY_MS);
    expect(save.firstElementChild?.className).toBe('spin');
    expect(save.getAttribute('aria-busy')).toBe('true');
    saved.reject(new ApiError(403, { title: 'forbidden', status: 403, code: 'forbidden', detail: 'Not allowed' }));
    await settle();
    expect(container.querySelector('.dlg')).toBeNull();
    expect(store.ui.toasts.map((t) => t.strong)).toContain('Refused');
  });
});

describe('teach bar Processing', () => {
  const understood: TeachResult = {
    outcome: 'not_understood',
    domainKey: null,
    intents: [],
    drafts: [],
    statements: [],
    caption: 'Try again',
    origin: 'text',
    originDetail: null,
    extractor: 'rules',
    degraded: false,
    llmOutcome: 'not_triggered',
    draftNotes: [],
    unresolved: [],
    segments: [],
  };
  let before: typeof store.s.activeCompany;
  beforeEach(() => {
    before = store.s.activeCompany;
    store.s.activeCompany = { sid: 'company-a' } as typeof before;
  });
  afterEach(() => {
    store.s.activeCompany = before;
    store.ui.processing = 0;
  });

  const status = (c: HTMLElement) => c.querySelector('#teachStatus') as HTMLElement;

  it('shows Processing in the status slot while a typed sentence is parsed, after 250 ms, for at least 400 ms', async () => {
    const parsed = deferred<TeachResult>();
    vi.spyOn(api, 'teachParse').mockReturnValue(parsed.promise);
    const { container } = render(<TeachStatus />);
    let done: Promise<boolean> = Promise.resolve(true);
    act(() => {
      done = teach('Insight sells services');
    });
    await advance(BUSY_DELAY_MS - 1);
    expect(status(container).querySelector('.spin')).toBeNull();
    expect(status(container).getAttribute('role')).toBe('status');
    await advance(1);
    expect(status(container).firstElementChild?.className).toBe('spin');
    expect(status(container).textContent).toBe('Processing');
    parsed.resolve(understood);
    await act(() => done);
    expect(status(container).textContent).toBe('Processing');
    await advance(STATUS_MIN_MS);
    expect(status(container).querySelector('.spin')).toBeNull();
    expect(status(container).textContent).toBe('');
  });

  it('counts queued spoken sentences and clears when the last is taught', async () => {
    const first = deferred<TeachResult>(),
      second = deferred<TeachResult>();
    vi.spyOn(api, 'teachParse').mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const { container } = render(<TeachStatus />);
    const stream = speechStream();
    act(() => {
      stream.sentence('Insight sells services');
      stream.sentence('It buys advisory');
    });
    expect(store.ui.processing).toBe(2);
    await advance(BUSY_DELAY_MS);
    expect(status(container).textContent).toBe('Processing · 1 queued');
    first.resolve(understood);
    await settle();
    expect(store.ui.processing).toBe(1);
    await advance(BUSY_DELAY_MS);
    expect(status(container).textContent).toBe('Processing');
    second.resolve(understood);
    await act(() => stream.settled());
    expect(store.ui.processing).toBe(0);
    await advance(STATUS_MIN_MS);
    expect(status(container).querySelector('.spin')).toBeNull();
  });

  it('clears on a refusal', async () => {
    const parsed = deferred<TeachResult>();
    vi.spyOn(api, 'teachParse').mockReturnValue(parsed.promise);
    const { container } = render(<TeachStatus />);
    let done: Promise<boolean> = Promise.resolve(true);
    act(() => {
      done = teach('Insight sells services');
    });
    await advance(BUSY_DELAY_MS);
    expect(status(container).textContent).toBe('Processing');
    parsed.reject(new ApiError(503, { title: 'busy', status: 503, code: 'busy', detail: 'Try later' }));
    await act(() => done);
    await advance(STATUS_MIN_MS);
    expect(status(container).querySelector('.spin')).toBeNull();
    expect(store.ui.processing).toBe(0);
  });

  it('never flashes for a parse that answers within 250 ms', async () => {
    vi.spyOn(api, 'teachParse').mockResolvedValue(understood);
    const { container } = render(<TeachStatus />);
    let done: Promise<boolean> = Promise.resolve(true);
    act(() => {
      done = teach('Insight sells services');
    });
    await act(() => done);
    await advance(BUSY_DELAY_MS * 2);
    expect(status(container).querySelector('.spin')).toBeNull();
    expect(status(container).textContent).toBe('');
  });
});
