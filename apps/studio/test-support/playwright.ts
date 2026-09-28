/**
 * Re-exports the test dependencies of tests/screenshots from the Studio package, where pnpm
 * installs them. The screenshot suite imports this module by relative path so it resolves the
 * same `@playwright/test` instance the runner uses without a workspace entry of its own.
 */
export * from '@playwright/test';
export { default as pixelmatch } from 'pixelmatch';
export { PNG } from 'pngjs';
