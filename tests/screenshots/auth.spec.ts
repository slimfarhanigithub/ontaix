/**
 * Studio-only baselines of the screens the reference does not have (ADR 0017 section 9): the
 * sign-in page, the "Choose a new password" page, and the platform portal's Organizations and
 * Platform audit log pages. Each is captured at 1440x900 and 1920x1080 in dark and light and
 * compared with a stored baseline under tests/screenshots/baselines at 0.1 percent tolerance.
 *
 * The Studio is opened with `?api=real`, so its calls reach the network, where this spec answers
 * the session and platform routes with fixtures. No fixture holds a credential.
 *
 * `--update-snapshots` writes the baselines of the running platform.
 */
import { test, expect, type Page, type Route } from '../../apps/studio/test-support/playwright';
import { animationsSettled, fontsReady, serveFontsLocally, TOLERANCE, VIEWPORTS, type Theme } from './harness';

const CSRF = 'screenshot-csrf-'.padEnd(43, 'x');

const problem = (status: number, code: string, detail: string) => ({
  status,
  contentType: 'application/problem+json',
  body: JSON.stringify({ type: `urn:ontaix:problem:${code}`, title: code, status, code, detail }),
});
const json = (body: unknown, status = 200) => ({ status, contentType: 'application/json', body: JSON.stringify(body) });
const paged = (items: unknown[]) => json({ items, page: 1, pageSize: 200, total: items.length });

const member = (mustChangePassword: boolean) => ({
  kind: 'member',
  account: { id: 'acc-1', email: 'ana@northwind.example', name: 'Ana Ruiz' },
  organization: { id: 'org-1', name: 'Northwind Industries', slug: 'northwind' },
  userId: 'u-1',
  support: null,
  csrfToken: CSRF,
  mustChangePassword,
  idleExpiresAt: '2026-09-28T09:30:00Z',
  absoluteExpiresAt: '2026-09-28T21:00:00Z',
});

const platform = {
  kind: 'platform',
  account: { id: 'acc-sa', email: 'admin@platform.example', name: 'Platform admin' },
  organization: null,
  userId: null,
  platformRoles: ['super_admin'],
  support: null,
  csrfToken: CSRF,
  mustChangePassword: false,
  idleExpiresAt: '2026-09-28T09:30:00Z',
  absoluteExpiresAt: '2026-09-28T21:00:00Z',
};

const org = (id: string, name: string, slug: string, companyMode: string, status: string, companies: number, users: number, createdAt: string) => ({
  id,
  name,
  slug,
  companyMode,
  status,
  companies,
  users,
  createdAt,
  disabledAt: status === 'disabled' ? createdAt : null,
});

const ORGANIZATIONS = [
  org('org-1', 'Northwind Industries', 'northwind', 'multiple', 'active', 2, 9, '2026-09-01T09:00:00Z'),
  org('org-2', 'Aurora Valves', 'aurora-valves', 'single', 'active', 1, 4, '2026-09-12T14:20:00Z'),
  org('org-3', 'Contoso Logistics', 'contoso-logistics', 'multiple', 'disabled', 3, 12, '2026-08-19T08:05:00Z'),
];

const AUDIT = [
  { id: 5, at: '2026-09-28T08:55:00Z', actor: { accountId: 'acc-sa', email: 'admin@platform.example' }, action: 'support_session_started', ok: true, organization: { id: 'org-1', name: 'Northwind Industries', slug: 'northwind' }, what: 'Opened a read-only support session: bindings check', clientIp: '10.0.0.4' },
  { id: 4, at: '2026-09-28T08:40:00Z', actor: { accountId: 'acc-sa', email: 'admin@platform.example' }, action: 'account_created', ok: true, organization: { id: 'org-2', name: 'Aurora Valves', slug: 'aurora-valves' }, what: 'Created the account of Mia Chen', clientIp: '10.0.0.4' },
  { id: 3, at: '2026-09-28T08:12:00Z', actor: null, action: 'sign_in_failed', ok: false, organization: null, what: 'A sign-in with an unknown email failed', clientIp: '10.0.0.9' },
  { id: 2, at: '2026-09-28T07:58:00Z', actor: { accountId: 'acc-sa', email: 'admin@platform.example' }, action: 'organization_disabled', ok: true, organization: { id: 'org-3', name: 'Contoso Logistics', slug: 'contoso-logistics' }, what: 'Disabled the organization Contoso Logistics', clientIp: '10.0.0.4' },
  { id: 1, at: '2026-09-28T07:30:00Z', actor: { accountId: 'acc-sa', email: 'admin@platform.example' }, action: 'sign_in', ok: true, organization: null, what: 'Signed in', clientIp: '10.0.0.4' },
];

type Answer = { status: number; contentType: string; body: string };

/** Answers the Studio's API calls for one screen; anything unlisted is a 404 problem. */
function serve(routes: Record<string, Answer>): (route: Route) => Promise<void> {
  return (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname.replace(/^\/api\/v1/, '');
    const key = `${req.method()} ${path}`;
    return route.fulfill(routes[key] ?? problem(404, 'not_found', `${key} is not part of this screen`));
  };
}

interface Screen {
  name: string;
  routes: Record<string, Answer>;
  /** What the page must show before the capture. */
  ready: string;
  /** What the page shows once mounted, before `drive` runs; the first token of `ready` when omitted. */
  mounted?: string;
  drive?: (page: Page) => Promise<void>;
}

const SCREENS: Screen[] = [
  {
    name: 'sign-in',
    routes: { 'GET /auth/session': problem(401, 'unauthorized', 'no session') },
    ready: 'form.dlg.sm #siPassword',
  },
  {
    name: 'choose-password',
    routes: { 'GET /auth/session': json(member(true)) },
    ready: 'form.dlg.sm #cp-confirm',
  },
  {
    name: 'platform-organizations',
    routes: { 'GET /auth/session': json(platform), 'GET /admin/organizations': paged(ORGANIZATIONS) },
    ready: '#lstOrganizations .tbl tbody tr',
  },
  {
    name: 'platform-audit',
    routes: { 'GET /auth/session': json(platform), 'GET /admin/organizations': paged(ORGANIZATIONS), 'GET /admin/audit': paged(AUDIT) },
    ready: '#lstPlatformAudit .tbl tbody tr',
    mounted: '#platformNav button[data-page="audit"]',
    drive: async (page) => {
      await page.click('#platformNav button[data-page="audit"]');
    },
  },
];

const themes: Theme[] = ['dark', 'light'];
const only = process.env.ONTAIX_SCENE?.split(',');
const onlyTheme = process.env.ONTAIX_THEME;

for (const vp of VIEWPORTS) {
  for (const screen of SCREENS) {
    if (only && !only.some((o) => screen.name.includes(o))) continue;
    for (const theme of themes) {
      if (onlyTheme && onlyTheme !== theme) continue;
      const name = `auth-${screen.name}-${theme}-${vp.width}x${vp.height}`;
      test(`${screen.name} · ${theme} · ${vp.width}x${vp.height}`, async ({ browser }) => {
        // The audit log shows its fixtures' times in the browser's zone, so every platform renders them in UTC.
        const ctx = await browser.newContext({ viewport: vp, timezoneId: 'UTC' });
        const page = await ctx.newPage();
        try {
          // No fake clock: nothing on these screens depends on the current time, and the fonts come from the repository as usual.
          await serveFontsLocally(page);
          await page.route(/\/api\/v1\//, serve(screen.routes));
          await page.goto('/?api=real');
          await page.waitForSelector(screen.mounted ?? screen.ready.split(' ')[0]);
          if (theme === 'light') await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'light'));
          if (screen.drive) await screen.drive(page);
          await page.waitForSelector(screen.ready);
          await fontsReady(page);
          await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
          // The window's or dialog's entrance animation runs in real time; it ends before the capture.
          await animationsSettled(page);
          await expect(page).toHaveScreenshot(`${name}.png`, { animations: 'disabled', caret: 'hide', maxDiffPixelRatio: TOLERANCE });
        } finally {
          await ctx.close();
        }
      });
    }
  }
}
