import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { API_BASE } from './api/client';
import { App } from './App';
import './styles/reference.css';

/**
 * Test hooks (seeded random source, in-browser mock API, `window.__ontaix`) exist only in dev
 * builds or when `VITE_ONTAIX_TEST_HOOKS=true` at build time; the modules behind them are
 * loaded on demand so a production build never carries them.
 */
const TEST_HOOKS = import.meta.env.DEV || import.meta.env.VITE_ONTAIX_TEST_HOOKS === 'true';

async function start(): Promise<void> {
  if (TEST_HOOKS) {
    const params = new URLSearchParams(location.search);
    const { seedFromLocation, setSource, traceDraws } = await import('./runtime/rng');
    const seed = seedFromLocation(location.search, import.meta.env.VITE_ONTAIX_SEED as string | undefined);
    if (seed !== null) {
      const { mulberry32 } = await import('./runtime/mulberry32');
      setSource(mulberry32(seed));
      const draws: [number, number][] = [];
      traceDraws((t, v) => draws.push([t, v]));
      const { store } = await import('./store/store');
      (window as unknown as { __ontaix: unknown }).__ontaix = { store, draws };
    }
    // Without a configured API the in-browser mock answers; `?api=mock` forces it.
    if (!import.meta.env.VITE_ONTAIX_API_URL || params.get('api') === 'mock') {
      const { installMockFetch } = await import('./api/mock/install');
      installMockFetch(API_BASE);
    }
  }
  const container = document.getElementById('root');
  if (!container) {
    throw new Error('Studio root element #root is missing from index.html');
  }
  createRoot(container).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

void start();
