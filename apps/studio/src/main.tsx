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
  let mock = false;
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
    mock = !import.meta.env.VITE_ONTAIX_API_URL || params.get('api') === 'mock';
    if (mock) {
      const [{ installMockFetch }, { createMockServer }, { liveEvents }, { store }] = await Promise.all([
        import('./api/mock/install'),
        import('./api/mock/server'),
        import('./api/events'),
        import('./store/store'),
      ]);
      // Concepts the mock proposes by itself divide with the draws it made, in the reference's order.
      installMockFetch(API_BASE, createMockServer(liveEvents, { rememberBirth: (c, l, d) => store.rememberBirth(c, l, d) }));
    }
  }
  if (!mock) {
    const { connectRealApi } = await import('./api/real');
    connectRealApi();
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
