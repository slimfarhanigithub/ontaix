/**
 * The drawer's More actions button (`#drMore`), the only button of the drawer's action row, and
 * its menu, which holds every action on a cell: Grow a concept from it, Lineage (a toggle) and
 * Expand; Rename and Move to domain; Delete. Each item keeps the id, visibility rule and effect
 * its action has elsewhere. The button and the menu are the shared MoreMenu.
 */
import { deleteNodeDialog, moveDialog, renameDialog } from '../admin/actions';
import { canDeleteFromDrawer } from '../admin/conceptDeletion';
import type { Node } from '../canvas/types';
import { t, useT } from '../i18n/i18n';
import type { store } from '../store/store';
import { useStore } from './dom';
import { canExpandFromDrawer, openExpandDialog } from './ExpandDialog';
import { MoreMenu, type MoreMenuItem } from './MoreMenu';

export type { MoreMenuIcon, MoreMenuItem } from './MoreMenu';

/** The items the menu offers for a cell, in order and in groups; none for a source. */
export function moreMenuItems(st: typeof store, n: Node, expanding: boolean): MoreMenuItem[] {
  const items: MoreMenuItem[] = [];
  if (n.kind !== 'source')
    items.push({
      id: 'drGrow',
      label: t('shell.drawer.grow'),
      icon: 'grow',
      group: 1,
      act: () => {
        const v = st.renderer?.v;
        st.openNewBox(n, (v ? v.W : innerWidth) * 0.35, (v ? v.H : innerHeight) * 0.4);
      },
    });
  if (n.kind === 'concept') items.push({ id: 'drLineage', label: t('shell.drawer.lineage'), icon: 'lineage', group: 1, checked: st.s.lineageNode === n, act: () => st.toggleLineage() });
  if (canExpandFromDrawer(n)) items.push({ id: 'drExpand', label: t('shell.drawer.expand'), icon: 'expand', group: 1, waiting: expanding, act: () => openExpandDialog(n) });
  if (canDeleteFromDrawer(n)) {
    items.push({ id: 'drRename', label: t('shell.drawer.rename'), icon: 'rename', group: 2, act: () => renameDialog(n) });
    items.push({ id: 'drMove', label: t('shell.drawer.move'), icon: 'move', group: 2, act: () => moveDialog(n) });
    items.push({ id: 'drDelete', label: t('common.delete'), icon: 'delete', group: 3, danger: true, act: () => deleteNodeDialog(n) });
  }
  return items;
}

export function DrawerMoreMenu({ node, expanding }: { node: Node; expanding: boolean }) {
  const st = useStore();
  const t = useT();
  const items = moreMenuItems(st, node, expanding);
  return <MoreMenu id="drMore" menuId="drMoreMenu" label={t('common.moreActions')} items={items} oxNew waiting={expanding} skipAnimation={() => st.s.SKIP} />;
}
