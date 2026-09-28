/**
 * The "Add a company" dialog. Markup and behaviour from
 * reference/ontaix-studio-reference.html lines 614-615 (`openAddCompany`).
 */
import { addCompany } from '../demo/story';
import { store } from '../store/store';
import { refStyle } from './dom';

export function openAddCompany(): void {
  store.openDialog({
    title: 'Add a company',
    sub: 'a new business-as-a-product in the same view',
    body: (
      <div className="form">
        <label>Company name</label>
        <input id="acName" placeholder="e.g. Aurora Valves" />
        <label>One line of context</label>
        <input id="acSub" placeholder="e.g. valve manufacturer · 2 plants · 640 people" />
        <label>Start with</label>
        <div ref={refStyle('display:grid;gap:8px')}>
          <label className="chk">
            <input type="radio" name="acSeed" value="seed" defaultChecked />
            <span>
              <b>Its own starter vocabulary</b>
              <small>13 concepts across the domain products, in its own words, waiting for approval</small>
            </span>
          </label>
          <label className="chk">
            <input type="radio" name="acSeed" value="empty" />
            <span>
              <b>One cell</b>
              <small>Teach it, import its documents, or grow it by hand</small>
            </span>
          </label>
        </div>
      </div>
    ),
    buttons: [
      { label: 'Cancel' },
      {
        label: 'Add company',
        cls: 'primary',
        onClick: (bk) => {
          const nameInput = bk.querySelector<HTMLInputElement>('#acName');
          const name = nameInput?.value.trim() || '';
          if (!name) {
            nameInput?.focus();
            return false;
          }
          const sub = bk.querySelector<HTMLInputElement>('#acSub')?.value.trim() || '';
          const seed = bk.querySelector<HTMLInputElement>('input[name=acSeed]:checked')?.value === 'seed';
          void addCompany(name, sub, seed).then((c) => {
            if (!c) return;
            store.caption(
              `${c.name} joins the view`,
              `A second company, with its own domain products, its own owners and its own words. ${seed ? 'Its starter vocabulary is waiting for approval.' : 'Teach it, import its documents, or click its cell to grow it.'}`,
            );
            store.toast2('Added', `${name}${seed ? ' · 13 proposals waiting on the canvas' : ''}`);
            if (store.ui.adminOpen) store.renderAdmin();
          });
        },
      },
    ],
  });
}
