import { act, cleanup, fireEvent, render } from '@testing-library/react';

import { api } from '../api/client';
import type { Proposal } from '../api/types';
import { store } from '../store/store';
import { AdminOverlay } from './AdminOverlay';
import { BUSY_DELAY_MS } from './busy';
import { Dialog } from './Dialog';
import { Panel } from './Panel';
import { useKeyboard } from './useKeyboard';

// The portal's pages load directory data; one button each stands in for them here.
vi.mock('../admin/AdminPortal', () => ({
  AdminNav: () => <button data-page="sources">Data sources</button>,
  AdminMain: () => <button>Add</button>,
}));

/** A promise with its resolve in hand. */
function deferred<T = void>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

const proposal = (id: string, title: string, openBelow = 0): Proposal =>
  ({
    id,
    type: 'concept',
    state: 'pending',
    title,
    heading: 'New concept',
    color: '#fff',
    deps: [],
    ready: true,
    html: `<b>${title}</b>`,
    why: '',
    relationIds: [],
    bindingIds: [],
    openBelow,
  }) as unknown as Proposal;

const dlg = () => document.querySelector('.dlg') as HTMLElement | null;
const tab = (shiftKey = false) => fireEvent.keyDown(document.activeElement as Element, { key: 'Tab', shiftKey });

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  store.ui.dialogs = [];
  store.ui.proposals = [];
  store.ui.adminOpen = false;
});

function opener(): HTMLButtonElement {
  const b = document.createElement('button');
  b.textContent = 'Open';
  document.body.appendChild(b);
  b.focus();
  return b;
}

describe('dialogs', () => {
  it('are named by their title, keep Tab inside and give focus back to the opener on close', async () => {
    const from = opener();
    render(<Dialog />);
    act(() => {
      store.openDialog({
        title: 'Rename Pump',
        body: <input id="nameField" />,
        buttons: [{ label: 'Cancel' }, { label: 'Save', cls: 'primary' }],
      });
    });
    const d = dlg() as HTMLElement;
    const title = document.getElementById(d.getAttribute('aria-labelledby') as string);
    expect(title?.textContent).toBe('Rename Pump');
    await act(() => vi.advanceTimersByTimeAsync(30));
    const field = document.getElementById('nameField') as HTMLInputElement;
    expect(document.activeElement).toBe(field);

    const close = d.querySelector('.dh .x') as HTMLElement;
    const save = d.querySelector('.df .btn.primary') as HTMLElement;
    save.focus();
    tab();
    expect(document.activeElement).toBe(close);
    tab(true);
    expect(document.activeElement).toBe(save);

    fireEvent.keyDown(document.activeElement as Element, { key: 'Escape' });
    expect(dlg()).toBeNull();
    expect(document.activeElement).toBe(from);
    from.remove();
  });

  it('close on Escape when the focus has left them', () => {
    render(<Dialog />);
    act(() => {
      store.openDialog({ title: 'Heads up', body: 'Text', buttons: [{ label: 'OK' }] });
    });
    (document.activeElement as HTMLElement | null)?.blur();
    act(() => {
      fireEvent.keyDown(document.body, { key: 'Escape' });
    });
    expect(dlg()).toBeNull();
  });

  it('keep the focus on the dialog while a focused button waits, so Escape still closes it', async () => {
    const wait = deferred();
    render(<Dialog />);
    act(() => {
      store.openDialog({ title: 'Save', body: 'Text', buttons: [{ label: 'Save', cls: 'primary', onClick: () => wait.promise }] });
    });
    const save = document.querySelector('.dlg .df .btn.primary') as HTMLButtonElement;
    save.focus();
    fireEvent.click(save);
    await act(() => vi.advanceTimersByTimeAsync(BUSY_DELAY_MS));
    expect(save.disabled).toBe(true);
    expect(document.activeElement).toBe(dlg());
    fireEvent.keyDown(document.activeElement as Element, { key: 'Escape' });
    expect(dlg()).toBeNull();
    wait.resolve();
  });
});

describe('the admin portal', () => {
  it('is named by its heading, keeps Tab inside its window and gives focus back when it closes', () => {
    const from = opener();
    const { container } = render(<AdminOverlay />);
    const admin = container.querySelector('#admin') as HTMLElement;
    expect(document.getElementById(admin.getAttribute('aria-labelledby') as string)?.textContent).toBe('Ontology Builder admin portal');
    act(() => {
      store.ui.adminOpen = true;
      store.bump();
    });
    const win = admin.querySelector('.win') as HTMLElement;
    const tabKey = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
    from.dispatchEvent(tabKey);
    expect(tabKey.defaultPrevented).toBe(true);
    expect(win.contains(document.activeElement)).toBe(true);
    act(() => {
      store.ui.adminOpen = false;
      store.bump();
    });
    expect(document.activeElement).toBe(from);
    from.remove();
  });
});

describe('destructive rejects', () => {
  it('Reject all asks first, and rejects only on confirmation', async () => {
    const rejectAll = vi.spyOn(api, 'rejectAll').mockResolvedValue({ caption: 'done' } as never);
    store.ui.proposals = [proposal('p-1', 'Pump'), proposal('p-2', 'Valve')];
    const panel = render(<Panel />);
    render(<Dialog />);
    fireEvent.click(panel.container.querySelector('#rejectAll') as HTMLElement);
    expect(rejectAll).not.toHaveBeenCalled();
    const d = dlg() as HTMLElement;
    expect(d.querySelector('.dh b')?.textContent).toBe('Reject 2 proposals?');
    expect(d.querySelector('.db')?.textContent).toBe('Every pending proposal is discarded. This cannot be undone.');
    const yes = d.querySelector('.df .btn.danger') as HTMLButtonElement;
    expect(yes.textContent).toBe('Reject all');
    expect(d.querySelector('.df .btn:not(.danger)')?.textContent).toBe('Cancel');
    await act(async () => {
      fireEvent.click(yes);
    });
    expect(rejectAll).toHaveBeenCalledTimes(1);
    expect(dlg()).toBeNull();
  });

  it('Cancel on Reject all rejects nothing', () => {
    const rejectAll = vi.spyOn(api, 'rejectAll');
    store.ui.proposals = [proposal('p-1', 'Pump')];
    const panel = render(<Panel />);
    render(<Dialog />);
    fireEvent.click(panel.container.querySelector('#rejectAll') as HTMLElement);
    expect(dlg()?.querySelector('.dh b')?.textContent).toBe('Reject 1 proposal?');
    fireEvent.click(dlg()?.querySelector('.df .btn:not(.danger)') as HTMLElement);
    expect(dlg()).toBeNull();
    expect(rejectAll).not.toHaveBeenCalled();
  });

  it('Reject asks first only when open proposals below go with it', async () => {
    const reject = vi.spyOn(api, 'reject').mockResolvedValue(undefined as never);
    store.ui.proposals = [proposal('p-1', 'Pump', 4), proposal('p-2', 'Valve', 1), proposal('p-3', 'Seal')];
    const panel = render(<Panel />);
    render(<Dialog />);
    const rejects = panel.container.querySelectorAll('.prop .act button.no');

    await act(async () => {
      fireEvent.click(rejects[2]);
    });
    expect(dlg()).toBeNull();
    expect(reject).toHaveBeenCalledWith('p-3');

    fireEvent.click(rejects[1]);
    expect(dlg()?.querySelector('.dh b')?.textContent).toBe('Reject Valve and the proposal below it?');
    fireEvent.click(dlg()?.querySelector('.df .btn:not(.danger)') as HTMLElement);

    fireEvent.click(rejects[0]);
    const d = dlg() as HTMLElement;
    expect(d.querySelector('.dh b')?.textContent).toBe('Reject Pump and the 4 proposals below it?');
    expect(d.querySelector('.db')?.textContent).toBe('Every proposal that grows from it is rejected with it. This cannot be undone.');
    expect(reject).toHaveBeenCalledTimes(1);
    await act(async () => {
      fireEvent.click(d.querySelector('.df .btn.danger') as HTMLElement);
    });
    expect(reject).toHaveBeenLastCalledWith('p-1');
  });
});

describe('single-letter shortcuts', () => {
  function Keys() {
    useKeyboard();
    return null;
  }
  const press = (key: string, target: EventTarget = document.body, init: KeyboardEventInit = {}) =>
    act(() => {
      target.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, ...init }));
    });

  it('act on the canvas from the page, not from fields, with modifiers or while a dialog is open', () => {
    const legend = vi.spyOn(store, 'toggleLegend').mockImplementation(() => undefined);
    render(<Keys />);
    press('l');
    expect(legend).toHaveBeenCalledTimes(1);

    for (const tag of ['input', 'select', 'textarea']) {
      const el = document.createElement(tag);
      document.body.appendChild(el);
      press('l', el);
      el.remove();
    }
    const editable = document.createElement('div');
    editable.contentEditable = 'true';
    Object.defineProperty(editable, 'isContentEditable', { value: true });
    document.body.appendChild(editable);
    press('l', editable);
    editable.remove();
    press('l', document.body, { ctrlKey: true });
    press('l', document.body, { altKey: true });
    press('l', document.body, { metaKey: true });
    expect(legend).toHaveBeenCalledTimes(1);

    store.ui.dialogs = [{ id: 1, title: 'x', body: null }];
    press('l');
    press('g');
    expect(legend).toHaveBeenCalledTimes(1);
    expect(store.ui.adminOpen).toBe(false);
  });

  it('with the admin portal open, only G closes it; Escape is left to an open dialog', () => {
    const legend = vi.spyOn(store, 'toggleLegend').mockImplementation(() => undefined);
    const open = vi.spyOn(store, 'openAdmin').mockImplementation(() => {
      store.ui.adminOpen = true;
    });
    const close = vi.spyOn(store, 'closeAdmin').mockImplementation(() => {
      store.ui.adminOpen = false;
    });
    const escape = vi.spyOn(store, 'escape').mockImplementation(() => undefined);
    render(<Keys />);
    press('g');
    expect(open).toHaveBeenCalledTimes(1);
    press('l');
    expect(legend).not.toHaveBeenCalled();

    store.ui.dialogs = [{ id: 1, title: 'x', body: null }];
    press('Escape');
    expect(close).not.toHaveBeenCalled();
    expect(escape).not.toHaveBeenCalled();
    store.ui.dialogs = [];

    press('g');
    expect(close).toHaveBeenCalledTimes(1);
  });
});
