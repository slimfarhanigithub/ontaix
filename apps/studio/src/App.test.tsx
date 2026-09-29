import { render, screen } from '@testing-library/react';

import { App } from './App';
import { installMockFetch } from './api/mock/install';

beforeAll(() => {
  // jsdom has no 2d canvas; the renderer only needs a context object that accepts calls.
  const ctx = new Proxy({} as CanvasRenderingContext2D, {
    get: (_t, prop) => (prop === 'canvas' ? {} : () => ({ addColorStop() {} })),
    set: () => true,
  });
  HTMLCanvasElement.prototype.getContext = (() => ctx) as unknown as typeof HTMLCanvasElement.prototype.getContext;
  installMockFetch();
});

describe('App', () => {
  it('renders the reference shell around the canvas', async () => {
    render(<App />);
    expect(screen.getByLabelText('Living ontology visualisation')).toBeInTheDocument();
    expect(screen.getByText('Proposed changes')).toBeInTheDocument();
    expect(screen.getByLabelText('How to read the lines')).toBeInTheDocument();
    expect(await screen.findByPlaceholderText('Teach Northwind Industries…')).toBeInTheDocument();
    expect(document.getElementById('next')).toBeNull();
    expect(document.getElementById('finalise')).toBeNull();
    expect(document.getElementById('sceneNum')).toBeNull();
  });
});
