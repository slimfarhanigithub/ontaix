import { createRoot } from 'react-dom/client';

import { API_BASE } from './api/client';
import { installMockFetch } from './api/mock/install';
import { App } from './App';
import { seedFromLocation, seedRandom, traceDraws } from './runtime/rng';
import { store } from './store/store';
import './styles/reference.css';

const params = new URLSearchParams(location.search);
const seed = seedFromLocation(location.search, import.meta.env.VITE_ONTAIX_SEED as string | undefined);
if (seed !== null) {
  seedRandom(seed);
  // Test mode exposes the store and the draw log so the screenshot harness can inspect both.
  const draws: [number, number][] = [];
  traceDraws((t, v) => draws.push([t, v]));
  (window as unknown as { __ontaix: unknown }).__ontaix = { store, draws };
}

// Without a configured API the in-browser mock answers; `?api=mock` forces it.
if (!import.meta.env.VITE_ONTAIX_API_URL || params.get('api') === 'mock') installMockFetch(API_BASE);

const container = document.getElementById('root');
if (!container) {
  throw new Error('Studio root element #root is missing from index.html');
}

createRoot(container).render(<App />);
