/**
 * The "Add a company" dialog. Markup and behaviour from
 * reference/ontaix-studio-reference.html lines 614-615 (`openAddCompany`).
 */
import { api } from '../api/client';
import type { Company } from '../canvas/types';
import { t } from '../i18n/i18n';
import { store } from '../store/store';
import { refStyle } from './dom';

/** Adds a company to the view and makes it the one being taught; its starter vocabulary arrives as proposals through events. */
async function addCompany(name: string, sub: string, seed: boolean): Promise<Company | null> {
  const created = await api.createCompany({ name, sub, start: seed ? 'starter_vocabulary' : 'one_cell' });
  const c = store.companyBySid(created.company.id);
  if (c) {
    store.s.activeCompany = c;
    store.renderCompanies();
  }
  return c;
}

export function openAddCompany(): void {
  store.openDialog({
    title: t('shell.addCompany.title'),
    sub: t('shell.addCompany.sub'),
    body: (
      <div className="form">
        <label>{t('shell.addCompany.name')}</label>
        <input id="acName" placeholder={t('shell.addCompany.namePlaceholder')} />
        <label>{t('shell.addCompany.context')}</label>
        <input id="acSub" placeholder={t('shell.addCompany.contextPlaceholder')} />
        <label>{t('shell.addCompany.startWith')}</label>
        <div ref={refStyle('display:grid;gap:8px')}>
          <label className="chk">
            <input type="radio" name="acSeed" value="seed" defaultChecked />
            <span>
              <b>{t('shell.addCompany.seed')}</b>
              <small>{t('shell.addCompany.seedDesc')}</small>
            </span>
          </label>
          <label className="chk">
            <input type="radio" name="acSeed" value="empty" />
            <span>
              <b>{t('shell.addCompany.oneCell')}</b>
              <small>{t('shell.addCompany.oneCellDesc')}</small>
            </span>
          </label>
        </div>
      </div>
    ),
    buttons: [
      { label: t('common.cancel') },
      {
        label: t('shell.addCompany.add'),
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
          return addCompany(name, sub, seed).then((c) => {
            if (!c) return;
            store.caption(
              t('shell.addCompany.joins', { name: c.name }),
              t('shell.addCompany.joinsText', { next: seed ? t('shell.addCompany.seedNext') : t('shell.addCompany.emptyNext') }),
            );
            store.toast2(t('shell.addCompany.added'), `${name}${seed ? t('shell.addCompany.addedSeed') : ''}`);
            if (store.ui.adminOpen) store.renderAdmin();
          });
        },
      },
    ],
  });
}
