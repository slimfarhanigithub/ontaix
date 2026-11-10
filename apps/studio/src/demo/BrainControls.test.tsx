import { act, fireEvent, render, screen } from '@testing-library/react';

import { applyLanguage } from '../i18n/language';
import { DockRight } from '../shell/DockRight';
import { DomainsCard } from '../shell/DomainsCard';
import { useKeyboard } from '../shell/useKeyboard';
import { Tools } from '../shell/Tools';
import { store } from '../store/store';
import { finishBrain } from './brainDemo';
import { BrainStatus } from './BrainControls';

function Keys() {
  useKeyboard();
  return null;
}

function Studio() {
  return (
    <>
      <Keys />
      <Tools />
      <BrainStatus />
    </>
  );
}

afterEach(() => {
  act(() => {
    finishBrain(store.s);
    store.bump();
    applyLanguage('en');
  });
});

describe('the demo brain controls', () => {
  it('starts and stops from the brain button, with nothing shown over the canvas', () => {
    render(<Studio />);
    const button = screen.getByRole('button', { name: 'Grow a demo brain' });
    expect(button).toHaveAttribute('aria-pressed', 'false');
    act(() => fireEvent.click(button));
    expect(screen.getByRole('button', { name: 'Grow a demo brain', pressed: true })).toBe(button);
    expect(button).toHaveAttribute('title', 'Stop the demo brain (Esc)');
    expect(screen.queryByRole('region')).toBeNull();
    expect(screen.queryByRole('progressbar')).toBeNull();
    const status = document.getElementById('brainStatus') as HTMLElement;
    expect(status).toHaveAttribute('aria-live', 'polite');
    expect(status).toHaveClass('sr');
    expect(status).toHaveTextContent('');
    act(() => fireEvent.click(button));
    expect(document.getElementById('brainStatus')).toBeNull();
    expect(screen.getByRole('button', { name: 'Grow a demo brain' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('fades the domains card, the legend and the shortcuts away while the demo grows, and brings them back on stop', () => {
    const { container } = render(
      <>
        <Studio />
        <DomainsCard />
        <DockRight>
          <span>legend</span>
        </DockRight>
      </>,
    );
    const docks = () => [container.querySelector('.dock-l'), container.querySelector('.dock-r')];
    for (const dock of docks()) expect(dock).not.toHaveClass('away');
    const button = screen.getByRole('button', { name: 'Grow a demo brain' });
    act(() => fireEvent.click(button));
    for (const dock of docks()) expect(dock).toHaveClass('away');
    act(() => fireEvent.click(button));
    for (const dock of docks()) expect(dock).not.toHaveClass('away');
  });

  it('reads in German when the portal language is German', () => {
    act(() => applyLanguage('de'));
    render(<Studio />);
    const button = screen.getByRole('button', { name: 'Ein Demo-Gehirn wachsen lassen' });
    act(() => fireEvent.click(button));
    expect(button).toHaveAttribute('title', 'Das Demo-Gehirn anhalten (Esc)');
  });

  it('stops on Escape', () => {
    render(<Studio />);
    act(() => fireEvent.click(screen.getByRole('button', { name: 'Grow a demo brain' })));
    act(() => {
      fireEvent.keyDown(window, { key: 'Escape' });
    });
    expect(document.getElementById('brainStatus')).toBeNull();
    expect(store.s.brain?.ending).not.toBeNull();
  });

  it('tells a screen reader once the brain has grown', () => {
    store.ui.skipAnimation = true;
    store.syncSkip();
    try {
      render(<Studio />);
      act(() => fireEvent.click(screen.getByRole('button', { name: 'Grow a demo brain' })));
      expect(document.getElementById('brainStatus')).toHaveTextContent(/^The demo brain has grown: [\d,]+ concepts\.$/);
    } finally {
      store.ui.skipAnimation = false;
      store.syncSkip();
    }
  });
});
