/**
 * The right-hand dock (`.dock-r`): the legend toggle, the legend and the shortcuts. Like the
 * left-hand dock it steps aside while the demo brain grows, so the canvas is the brain's alone,
 * and comes back once the demo stops.
 */
import type { ReactNode } from 'react';

import { brainRunning } from '../demo/BrainControls';
import { useStore } from './dom';

export function DockRight({ children }: { children: ReactNode }) {
  const st = useStore();
  return <div className={`dock-r${brainRunning(st) ? ' away' : ''}`}>{children}</div>;
}
