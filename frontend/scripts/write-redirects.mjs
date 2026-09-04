/**
 * Generate `public/_redirects` for a Netlify deploy.
 *
 * Netlify cannot read environment variables from `netlify.toml`, so the proxy
 * rule that points `/api/*` at the deployed backend is written here at build
 * time from `API_PROXY_TARGET`. Proxying keeps the browser on one origin, which
 * means no CORS, no mixed-content problems, and no backend URL in the bundle.
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const publicDir = resolve(here, '..', 'public');
const target = (process.env.API_PROXY_TARGET || '').trim().replace(/\/+$/, '');

if (!target) {
  console.error(
    '\nAPI_PROXY_TARGET is not set.\n' +
      'Set it to the base URL of the deployed backend, e.g.\n' +
      '  API_PROXY_TARGET=https://cyberwatch-api.onrender.com\n' +
      'In Netlify: Site configuration -> Environment variables.\n'
  );
  process.exit(1);
}

if (!/^https?:\/\//.test(target)) {
  console.error(`\nAPI_PROXY_TARGET must be an absolute http(s) URL, got: ${target}\n`);
  process.exit(1);
}

// First match wins, so the API rule has to precede the SPA fallback.
const rules = [
  `/api/*  ${target}/api/:splat  200`,
  '/*      /index.html           200',
  '',
].join('\n');

mkdirSync(publicDir, { recursive: true });
writeFileSync(resolve(publicDir, '_redirects'), rules, 'utf8');
console.log(`_redirects written: /api/* -> ${target}/api/:splat`);
