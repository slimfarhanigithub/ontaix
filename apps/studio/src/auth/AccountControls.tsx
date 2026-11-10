/**
 * `#adminAccount`, in the head of the admin portal and of the platform portal before the ×:
 * the signed-in email, `Switch organization` for a member of several organizations, `Language`,
 * `Change password`, `Sign out`, and `End support` while a super admin's support session is
 * open. Rendered only with a live session; a development identity header has none.
 */
import { failed } from '../admin/adminData';
import { LANGUAGE_NAMES, LANGUAGES, useLanguage, useT } from '../i18n/i18n';
import { BusyButton } from '../shell/busy';
import { refStyle } from '../shell/dom';
import { MoreMenu, type MoreMenuItem } from '../shell/MoreMenu';
import { auth, useAuth } from './authStore';
import { openChangePassword } from './ChangePasswordDialog';

/** The controls take the right of the head, before its × when the head has one. */
export function AccountControls() {
  const { session } = useAuth();
  const t = useT();
  const language = useLanguage();
  if (!session) return null;
  const several = session.kind === 'member' && (session.organizations ?? []).length > 1;
  // Each language is named in itself, so a reader finds theirs whatever the portal shows.
  const languages: MoreMenuItem[] = LANGUAGES.map((l) => ({
    id: `language-${l}`,
    label: LANGUAGE_NAMES[l],
    group: 1,
    radio: true,
    checked: l === language,
    attrs: { lang: l, 'data-language': l },
    act: () => auth.chooseLanguage(l).catch(failed),
  }));
  return (
    <div id="adminAccount" ref={refStyle('display:inline-flex;align-items:center;gap:8px;margin-left:auto')}>
      <span>{session.account.email}</span>
      {several ? (
        <button className="btn" id="switchOrganization" onClick={() => auth.switchOrganization()}>
          {t('auth.account.switchOrganization')}
        </button>
      ) : null}
      <MoreMenu id="language" menuId="languageMenu" label={t('common.language')} className="btn" items={languages} content={t('common.language')} />
      <button className="btn" id="changePassword" onClick={() => openChangePassword()}>
        {t('auth.account.changePassword')}
      </button>
      <BusyButton className="btn" id="signOut" onClick={() => auth.signOut()}>
        {t('auth.account.signOut')}
      </BusyButton>
      {session.support ? (
        <BusyButton className="btn" id="endSupport" onClick={() => auth.endSupport().catch(failed)}>
          {t('auth.account.endSupport')}
        </BusyButton>
      ) : null}
    </div>
  );
}
