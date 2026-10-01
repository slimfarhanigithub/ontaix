/**
 * Sign in and see only your own organization (ADR 0017). The super admin created by the global
 * setup signs in on the sign-in page, creates a second organization and one account in it and
 * one in the demo organization, each with a password generated for this run. Each member then
 * signs in on the sign-in page, chooses a new password, and the Studio shows only the companies
 * of their own organization: Northwind and Aurora for the demo member, the other organization's
 * one company for the other member.
 */
import { randomBytes } from 'node:crypto';

import { expect, test, type Browser, type Page } from '../../apps/studio/test-support/playwright';

const SUPER_ADMIN_EMAIL = process.env.E2E_SUPER_ADMIN_EMAIL || '';
const SUPER_ADMIN_PASSWORD = process.env.E2E_SUPER_ADMIN_PASSWORD || '';
const OTHER_COMPANY = 'Elsewhere Holdings';

interface Account {
  email: string;
  password: string;
}

function generated(): string {
  return randomBytes(18).toString('base64url');
}

async function signIn(page: Page, account: Account): Promise<void> {
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible();
  await page.getByLabel('Email').fill(account.email);
  await page.getByLabel('Password', { exact: true }).fill(account.password);
  await page.getByRole('button', { name: 'Sign in' }).click();
}

/** A JSON call from inside the signed-in page, with the session's CSRF token on writes. */
async function call<T>(page: Page, method: string, path: string, body?: unknown): Promise<T> {
  return page.evaluate(
    async ({ method, path, body }) => {
      const session = await (await fetch('/api/v1/auth/session')).json();
      const res = await fetch(`/api/v1${path}`, {
        method,
        headers: { 'content-type': 'application/json', 'X-CSRF-Token': session.csrfToken },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const text = await res.text();
      if (!res.ok) throw new Error(`${method} ${path} answered ${res.status}: ${text}`);
      return (text ? JSON.parse(text) : undefined) as T;
    },
    { method, path, body },
  );
}

async function memberSignsIn(browser: Browser, account: Account): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await signIn(page, account);
  await expect(page.getByText('Choose a new password')).toBeVisible();
  const chosen = generated();
  await page.getByLabel('Current password').fill(account.password);
  await page.getByLabel('New password', { exact: true }).fill(chosen);
  await page.getByLabel('Confirm new password').fill(chosen);
  await page.getByRole('button', { name: 'Save password' }).click();
  await page.waitForFunction(() => document.documentElement.dataset.ontaixReady === 'ready');
  return page;
}

async function companyNames(page: Page): Promise<string[]> {
  const scene = await call<{ companies: { name: string }[] }>(page, 'GET', '/scene');
  return scene.companies.map((c) => c.name).sort();
}

test('a member signs in and sees only their own organization', async ({ browser }) => {
  expect(SUPER_ADMIN_EMAIL, 'the global setup creates the super admin').not.toBe('');

  const admin = await (await browser.newContext()).newPage();
  await signIn(admin, { email: SUPER_ADMIN_EMAIL, password: SUPER_ADMIN_PASSWORD });
  await expect(admin.getByText('Ontaix platform')).toBeVisible();

  const organizations = await call<{ items: { id: string; slug: string }[] }>(admin, 'GET', '/admin/organizations?pageSize=200');
  const demo = organizations.items.find((o) => o.slug === 'demo');
  expect(demo, 'the demo tenant is an organization').toBeTruthy();
  const other = await call<{ id: string }>(admin, 'POST', '/admin/organizations', {
    name: `E2E Other ${randomBytes(3).toString('hex')}`,
    companyMode: 'single',
  });

  const groupId = async (organizationId: string, name: string): Promise<string> => {
    const groups = await call<{ id: string; name: string }[]>(admin, 'GET', `/admin/organizations/${organizationId}/groups`);
    const group = groups.find((g) => g.name === name);
    if (!group) throw new Error(`no group ${name}`);
    return group.id;
  };
  const addUser = async (organizationId: string, group: string): Promise<Account> => {
    const account = { email: `e2e-${randomBytes(4).toString('hex')}@org.test`, password: generated() };
    await call(admin, 'POST', `/admin/organizations/${organizationId}/users`, {
      email: account.email,
      name: 'E2E Member',
      password: account.password,
      groupIds: [await groupId(organizationId, group)],
    });
    return account;
  };
  const demoMember = await addUser(demo!.id, 'All employees');
  const otherMember = await addUser(other.id, 'Administrators');

  const otherPage = await memberSignsIn(browser, otherMember);
  await call(otherPage, 'POST', '/companies', { name: OTHER_COMPANY, sub: 'The other organization', start: 'one_cell' });
  expect(await companyNames(otherPage)).toEqual([OTHER_COMPANY]);

  const demoPage = await memberSignsIn(browser, demoMember);
  const names = await companyNames(demoPage);
  expect(names).toEqual(expect.arrayContaining(['Northwind Industries', expect.stringMatching(/^Aurora/)]));
  expect(names).not.toContain(OTHER_COMPANY);
  await expect(demoPage.locator('#companySel option')).not.toContainText([OTHER_COMPANY]);
  await expect(demoPage.locator('#companySel option', { hasText: 'Northwind Industries' })).toHaveCount(1);

  await otherPage.reload();
  await otherPage.waitForFunction(() => document.documentElement.dataset.ontaixReady === 'ready');
  expect(await companyNames(otherPage)).toEqual([OTHER_COMPANY]);
});
