import { act, cleanup, fireEvent, render } from '@testing-library/react';

import { store } from '../store/store';
import { Header } from './Header';
import { Panel } from './Panel';

vi.mock('../auth/authStore', () => ({ useAuth: () => ({ session: null }) }));

describe('the changes sheet under 900 px', () => {
  /** The listeners the Panel puts on the 900 px query, to cross it by hand. */
  let changes: (() => void)[] = [];
  beforeEach(() => {
    changes = [];
    vi.stubGlobal(
      'matchMedia',
      (q: string) =>
        ({
          matches: true,
          media: q,
          addEventListener: (_: string, fn: () => void) => changes.push(fn),
          removeEventListener: () => {},
        }) as unknown as MediaQueryList,
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    document.body.classList.remove('panel-sheet', 'panel-off');
    store.ui.panelSheet = false;
    store.ui.panelOff = false;
  });

  it('Show changes opens the sheet with the focus on its ×, and × closes it with the focus back on Show changes', () => {
    render(
      <>
        <Header />
        <Panel />
      </>,
    );
    const show = document.getElementById('panelShow') as HTMLButtonElement;
    const hide = document.getElementById('panelHide') as HTMLButtonElement;

    act(() => {
      show.focus();
      fireEvent.click(show);
    });
    expect(document.body.classList.contains('panel-sheet')).toBe(true);
    expect(document.activeElement).toBe(hide);

    act(() => {
      fireEvent.click(hide);
    });
    expect(document.body.classList.contains('panel-sheet')).toBe(false);
    expect(document.activeElement).toBe(show);
  });

  it('crossing 900 px closes an open sheet', () => {
    render(<Panel />);
    act(() => store.togglePanel());
    expect(document.body.classList.contains('panel-sheet')).toBe(true);
    act(() => changes.forEach((fn) => fn()));
    expect(document.body.classList.contains('panel-sheet')).toBe(false);
    expect(store.ui.panelSheet).toBe(false);
  });

  it('takes no focus when it renders closed', () => {
    render(<Panel />);
    expect(document.activeElement).toBe(document.body);
  });
});
