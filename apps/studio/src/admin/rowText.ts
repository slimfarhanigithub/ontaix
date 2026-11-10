/**
 * Setting-row texts the Studio adds to the reference's admin pages: a description for each row
 * the reference leaves without one, keyed by the row's English title, and the Appearance page's
 * Skip animation row. Every text is read in the portal language when it is accessed, so the
 * pages and the screenshot harness, which adds the same texts to the reference page, read the
 * same words.
 */
import { t } from '../i18n/i18n';

/** Descriptions of the Tenant settings rows the reference leaves empty, by the row's English title. */
export const ADDED_DESCRIPTIONS: Record<string, string> = {
  get 'Approval required for every change'() {
    return t('admin.settings.approvalRequired.desc');
  },
  get 'Several companies in one view'() {
    return t('admin.settings.multiCompany.desc');
  },
  get 'Show the relationship legend'() {
    return t('admin.settings.legend.desc');
  },
};

/** The Appearance page's Motion section: its heading, the row title and the row description. */
export const SKIP_ANIMATION_ROW = {
  get heading(): string {
    return t('admin.appearance.motion');
  },
  get title(): string {
    return t('admin.appearance.skip.title');
  },
  get desc(): string {
    return t('admin.appearance.skip.desc');
  },
};
