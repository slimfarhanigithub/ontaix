/**
 * The actions of a list row: the primary action stays a visible button, every other action sits
 * behind one `⋯` button in the shared More actions menu, so a row never crowds its cell. Each
 * menu item keeps the `data-fn` or `data-act` its action has always carried, so the admin
 * tests and the screenshot scenes find it by the same name once the menu is open. An item whose
 * action waits on the API (a deletion impact, for instance) shows the waiting ring on the `⋯`
 * button until it settles, as the row's own button did.
 */
import { useState, type ReactNode } from 'react';

import { MoreMenu, type MoreMenuItem } from '../shell/MoreMenu';

export interface RowAction extends Omit<MoreMenuItem, 'act'> {
  act: () => void | Promise<unknown>;
}

export interface RowActionsProps {
  /** A stable id for the row, naming the button and its menu. */
  id: string;
  /** The visible primary action(s), rendered before the menu button. */
  primary?: ReactNode;
  /** The other actions, in groups; a danger item reads in red. The menu is absent when empty. */
  items: RowAction[];
  /** Marks the menu button as an owner addition absent from the reference. */
  oxNew?: boolean;
}

export function RowActions({ id, primary, items, oxNew }: RowActionsProps) {
  const [waiting, setWaiting] = useState(false);
  const menuItems: MoreMenuItem[] = items.map((it) => ({
    ...it,
    act: () => {
      const r = it.act();
      if (r && typeof (r as Promise<unknown>).then === 'function') {
        setWaiting(true);
        void (r as Promise<unknown>).finally(() => setWaiting(false));
      }
    },
  }));
  return (
    <>
      {primary}
      {items.length ? <MoreMenu id={`${id}More`} menuId={`${id}Menu`} label="More actions" items={menuItems} oxNew={oxNew} waiting={waiting} /> : null}
    </>
  );
}
