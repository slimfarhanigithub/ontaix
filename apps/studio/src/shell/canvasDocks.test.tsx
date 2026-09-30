import { act, fireEvent, render } from '@testing-library/react';

import { Appearance, TenantSettings } from '../admin/pages/PortalPages';
import { ADDED_DESCRIPTIONS, SKIP_ANIMATION_ROW } from '../admin/rowText';
import type { Settings } from '../api/types';
import { store } from '../store/store';
import { SKIP_ANIMATION_KEY } from '../store/skipAnimation';
import { DomainsCard } from './DomainsCard';
import { Header } from './Header';
import { Hint } from './Hint';
import { LEGEND, Legend } from './Legend';
import { Tools } from './Tools';
import { useKeyboard } from './useKeyboard';

const settings: Settings = {
  voice: true,
  importDocs: true,
  liveTeaching: true,
  everyoneTeaches: false,
  approvalRequired: true,
  twoApprovers: false,
  autoAttrs: false,
  notifyOwners: true,
  multiCompany: true,
  crossCompany: true,
  animations: true,
  coverageDefault: false,
  legend: true,
  readOnlyConnectors: true,
  refresh: '15 min',
  agentAccess: true,
  costCap: true,
  llmMonthlyTokenCap: 2_000_000,
  ocrMonthlyPageCap: 1000,
};

function Keys() {
  useKeyboard();
  return null;
}

beforeEach(() => {
  localStorage.removeItem(SKIP_ANIMATION_KEY);
  store.ui.skipAnimation = false;
  store.ui.settings = { ...settings };
  store.ui.legendOff = false;
  store.syncSkip();
});

describe('the relationship legend', () => {
  it('labels each line in one or two words, with the explanation as tooltip and screen-reader text', () => {
    const { container } = render(<Legend />);
    const rows = [...container.querySelectorAll('#legend li.row')];
    expect(rows.map((r) => r.querySelector('b')?.textContent)).toEqual(['Relation', 'Is a', 'Equivalent', 'Conflict', 'Data binding', 'Pending']);
    for (const [i, row] of rows.entries()) {
      const label = row.querySelector('b')?.textContent ?? '';
      expect(label.split(' ').length).toBeLessThanOrEqual(2);
      expect(row.getAttribute('title')).toBe(LEGEND[i].detail);
      expect(row.querySelector('.sr')?.textContent).toBe(`: ${LEGEND[i].detail}`);
      expect(row.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true');
      expect(row.querySelector('svg text')).toBeNull();
    }
  });

  it('toggles from its button, which names what it controls', () => {
    const { container } = render(<Legend />);
    const toggle = container.querySelector('#legendToggle') as HTMLButtonElement;
    expect(toggle.getAttribute('aria-controls')).toBe('legend');
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    fireEvent.click(toggle);
    expect(toggle.textContent).toBe('Show legend');
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(container.querySelector('#legend')?.classList.contains('off')).toBe(true);
  });
});

describe('the canvas docks', () => {
  it('lists the shortcuts one per item, without skip animation', () => {
    const { container } = render(<Hint />);
    const items = [...container.querySelectorAll('.hint li')].map((li) => li.textContent);
    expect(items).toEqual(['P changes', 'D domains', 'I import · drop a file', 'C coverage', 'A arrange', 'click new concept', 'drop on a cell relate', 'wheel zoom', 'F full screen']);
    expect(container.textContent).not.toMatch(/skip/i);
  });

  it('stacks the domains toggle above its card in the left dock', () => {
    const { container } = render(<DomainsCard />);
    const dock = container.querySelector('.dock-l') as HTMLElement;
    expect([...dock.children].map((c) => c.id)).toEqual(['domainsToggle', 'domains']);
    expect((dock.firstElementChild as HTMLElement).getAttribute('style')).toBeNull();
    expect(dock.firstElementChild?.getAttribute('aria-controls')).toBe('domains');
  });

  it('puts Show changes in the header row after the admin button, never on top of it', () => {
    const { container } = render(<Header />);
    const row = container.querySelector('header .scene > div') as HTMLElement;
    expect([...row.querySelectorAll('button')].map((b) => b.id)).toEqual(['adminOpen', 'panelShow']);
    expect(row.querySelector('#panelShow')?.className).toBe('admin-open');
    expect((row.querySelector('#panelShow') as HTMLElement).style.position).toBe('');
  });
});

describe('Skip animation', () => {
  it('is not a tool button', () => {
    const { container } = render(<Tools />);
    expect(container.querySelector('#skip')).toBeNull();
    expect(container.textContent).not.toMatch(/skip|animations off/i);
  });

  it('is a setting on the Appearance page, remembered in this browser', () => {
    const { container } = render(<Appearance />);
    const heading = [...container.querySelectorAll('h3')].find((h) => h.textContent === SKIP_ANIMATION_ROW.heading);
    const row = heading?.nextElementSibling as HTMLElement;
    expect(row.className).toBe('set');
    expect(row.querySelector('b')?.textContent).toBe('Skip animation');
    expect(row.querySelector('p')?.textContent).toBe(SKIP_ANIMATION_ROW.desc);
    const tg = row.querySelector('[data-act="skipAnimation"]') as HTMLButtonElement;
    expect(tg.getAttribute('aria-pressed')).toBe('false');
    expect(tg.textContent).toBe('Enable');

    fireEvent.click(tg);

    expect(store.s.SKIP).toBe(true);
    expect(localStorage.getItem(SKIP_ANIMATION_KEY)).toBe('1');
    expect((container.querySelector('[data-act="skipAnimation"]') as HTMLElement).getAttribute('aria-pressed')).toBe('true');
    expect(container.querySelector('[data-act="skipAnimation"]')?.textContent).toBe('Disable');
  });

  it('still follows the S key, and the tenant turning animations off skips them too', () => {
    render(<Keys />);
    act(() => {
      fireEvent.keyDown(window, { key: 's' });
    });
    expect(store.ui.skipAnimation).toBe(true);
    expect(store.s.SKIP).toBe(true);
    act(() => {
      fireEvent.keyDown(window, { key: 's' });
    });
    expect(store.s.SKIP).toBe(false);
    expect(localStorage.getItem(SKIP_ANIMATION_KEY)).toBe('0');

    store.ui.settings = { ...settings, animations: false };
    store.applySettings();
    expect(store.s.SKIP).toBe(true);
    expect(store.ui.skipAnimation).toBe(false);
  });
});

describe('the admin setting rows', () => {
  it('gives every row a description', () => {
    const { container } = render(<TenantSettings />);
    const rows = [...container.querySelectorAll('.set')];
    expect(rows.length).toBeGreaterThan(10);
    for (const row of rows) expect(row.querySelector('p')?.textContent?.trim()).toBeTruthy();
    for (const [title, desc] of Object.entries(ADDED_DESCRIPTIONS)) {
      const row = rows.find((r) => r.querySelector('b')?.textContent === title);
      expect(row?.querySelector('p')?.textContent).toBe(desc);
    }
  });
});
