import { act, fireEvent, render, screen } from '@testing-library/react';

import { useKeyboard } from '../shell/useKeyboard';
import { Tools } from '../shell/Tools';
import { store } from '../store/store';
import { finishBrain } from './brainDemo';
import { BrainBar } from './BrainControls';

function Keys() {
  useKeyboard();
  return null;
}

function Studio() {
  return (
    <>
      <Keys />
      <Tools />
      <BrainBar />
    </>
  );
}

afterEach(() => {
  act(() => {
    finishBrain(store.s);
    store.bump();
  });
});

describe('the demo brain controls', () => {
  it('starts from the brain button, shows the demo bar and stops from its Stop button', () => {
    render(<Studio />);
    const button = screen.getByRole('button', { name: 'Grow a demo brain' });
    expect(button).toHaveAttribute('aria-pressed', 'false');
    expect(document.getElementById('brainBar')).toBeNull();
    act(() => fireEvent.click(button));
    expect(screen.getByRole('button', { name: 'Grow a demo brain', pressed: true })).toBe(button);
    expect(button).toHaveAttribute('title', 'Stop the demo brain (Esc)');
    const bar = screen.getByRole('region', { name: 'Demo brain' });
    expect(bar).toHaveTextContent('Starting a demo brain');
    expect(bar).toHaveTextContent('not saved');
    expect(screen.getByRole('progressbar', { name: 'Growth' })).toHaveAttribute('aria-valuenow', '0');
    act(() => fireEvent.click(document.getElementById('brainStop') as HTMLElement));
    expect(document.getElementById('brainBar')).toBeNull();
    expect(screen.getByRole('button', { name: 'Grow a demo brain' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('pauses and resumes from the demo bar', () => {
    render(<Studio />);
    act(() => fireEvent.click(screen.getByRole('button', { name: 'Grow a demo brain' })));
    act(() => fireEvent.click(screen.getByRole('button', { name: 'Pause the demo brain' })));
    expect(screen.getByRole('region', { name: 'Demo brain' })).toHaveTextContent('Demo brain paused');
    expect(store.s.brain?.pausedAt).not.toBeNull();
    act(() => fireEvent.click(screen.getByRole('button', { name: 'Resume the demo brain' })));
    expect(store.s.brain?.pausedAt).toBeNull();
  });

  it('stops on Escape', () => {
    render(<Studio />);
    act(() => fireEvent.click(screen.getByRole('button', { name: 'Grow a demo brain' })));
    act(() => {
      fireEvent.keyDown(window, { key: 'Escape' });
    });
    expect(document.getElementById('brainBar')).toBeNull();
    expect(store.s.brain?.ending).not.toBeNull();
  });

  it('offers Replay once the brain has grown', () => {
    store.ui.skipAnimation = true;
    store.syncSkip();
    try {
      render(<Studio />);
      act(() => fireEvent.click(screen.getByRole('button', { name: 'Grow a demo brain' })));
      expect(screen.getByRole('region', { name: 'Demo brain' })).toHaveTextContent('Demo brain grown');
      expect(screen.getByRole('button', { name: 'Grow the demo brain again' })).toBeInTheDocument();
      expect(screen.getByRole('progressbar', { name: 'Growth' })).toHaveAttribute('aria-valuenow', '100');
    } finally {
      store.ui.skipAnimation = false;
      store.syncSkip();
    }
  });
});
