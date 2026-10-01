/**
 * The Studio: the canvas and the shell around it, in the element order of
 * reference/ontaix-studio-reference.html lines 185-233.
 */
import { useEffect } from 'react';

import { AdminOverlay } from './shell/AdminOverlay';
import { NewBox, LinkBox } from './shell/Boxes';
import { CanvasView } from './shell/CanvasView';
import { Dialog } from './shell/Dialog';
import { DomainsCard } from './shell/DomainsCard';
import { Drawer } from './shell/Drawer';
import { Header } from './shell/Header';
import { Hint } from './shell/Hint';
import { Legend } from './shell/Legend';
import { Panel } from './shell/Panel';
import { SelectionBar } from './shell/SelectionBar';
import { TeachBar } from './shell/TeachBar';
import { Tools } from './shell/Tools';
import { Toasts } from './shell/Toasts';
import { useKeyboard } from './shell/useKeyboard';
import { store } from './store/store';

export function App() {
  useKeyboard();
  useEffect(() => {
    void store.load();
  }, []);
  return (
    <>
      <CanvasView />
      <Header />
      <Toasts />
      <AdminOverlay />
      <Tools />
      <SelectionBar />
      <TeachBar />
      <Panel />
      <Drawer />
      <NewBox />
      <LinkBox />
      <DomainsCard />
      <Legend />
      <Hint />
      <Dialog />
    </>
  );
}
