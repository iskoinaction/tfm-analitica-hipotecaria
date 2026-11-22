#!/usr/bin/env node
/**
 * Comprueba la web compilada (dist/) con Playwright: sin errores de consola, sin scroll horizontal a 390 px y
 * genera capturas JPEG en docs/screenshots/. Uso: npm run build && npm run screenshots
 * Playwright no es dependencia del proyecto: se resuelve desde PLAYWRIGHT_PATH (carpeta node_modules) o el entorno.
 */
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const SITE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DIST = path.join(SITE, 'dist');
const OUT = path.join(SITE, 'docs', 'screenshots');
const req = createRequire(process.env.PLAYWRIGHT_PATH ? path.join(process.env.PLAYWRIGHT_PATH, 'x.js') : import.meta.url);
const { chromium } = req('playwright');
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.png': 'image/png', '.jpg': 'image/jpeg' };

const server = http.createServer((q, r) => {
  let p = decodeURIComponent(new URL(q.url, 'http://x').pathname);
  if (p === '/') p = '/index.html';
  const f = path.join(DIST, p);
  if (!f.startsWith(DIST) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { r.writeHead(404); r.end('no'); return; }
  r.writeHead(200, { 'content-type': MIME[path.extname(f)] ?? 'application/octet-stream' }); fs.createReadStream(f).pipe(r);
});
await new Promise((ok) => server.listen(4179, ok));
const base = 'http://localhost:4179/';
fs.mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {});
const problems = [];
const SECTIONS = ['portada', 'arquitectura', 'fuentes', 'panel', 'economia', 'econometria', 'ml', 'predicciones', 'simulador', 'resultados'];

for (const [w, h, tag] of [[1440, 900, 'desktop'], [390, 844, 'movil']]) {
  for (const scheme of ['light', 'dark']) {
    if (scheme === 'dark' && tag === 'movil') continue;
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme, reducedMotion: 'reduce', deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) problems.push(`[${tag}/${scheme}] console.${m.type()}: ${m.text()}`); });
    page.on('pageerror', (e) => problems.push(`[${tag}/${scheme}] pageerror: ${e.message}`));
    page.on('requestfailed', (r) => problems.push(`[${tag}/${scheme}] requestfailed: ${r.url()}`));
    page.on('response', (r) => { if (r.status() >= 400) problems.push(`[${tag}/${scheme}] HTTP ${r.status()}: ${r.url()}`); });
    await page.goto(base, { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);
    const sw = await page.evaluate(() => ({ s: document.documentElement.scrollWidth, c: document.documentElement.clientWidth }));
    if (sw.s > sw.c) problems.push(`[${tag}/${scheme}] scroll horizontal: scrollWidth ${sw.s} > clientWidth ${sw.c}`);
    await page.addStyleTag({ content: '.topbar{position:static!important}.sim__results{position:static!important}' });
    for (const id of SECTIONS) {
      const el = page.locator(`#${id}`);
      await el.scrollIntoViewIfNeeded(); await page.waitForTimeout(450);
      const name = `${id}-${tag}${scheme === 'dark' ? '-oscuro' : ''}.jpg`;
      if (scheme === 'dark' && !['portada', 'panel', 'simulador'].includes(id)) continue;
      await el.screenshot({ path: path.join(OUT, name), type: 'jpeg', quality: 62 });
    }
    if (scheme === 'light') {
      await page.goto(base + '#estado', { waitUntil: 'networkidle' }); await page.waitForTimeout(500);
      const sw2 = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      if (sw2 > 0) problems.push(`[${tag}] scroll horizontal en vista Estado: +${sw2}px`);
      await page.screenshot({ path: path.join(OUT, `estado-${tag}.jpg`), type: 'jpeg', quality: 62, fullPage: false });
    }
    await ctx.close();
  }
}
await browser.close(); server.close();
let total = 0; for (const f of fs.readdirSync(OUT)) total += fs.statSync(path.join(OUT, f)).size;
console.log(`Capturas: ${fs.readdirSync(OUT).length} ficheros, ${(total / 1048576).toFixed(2)} MB`);
if (problems.length) { console.log('PROBLEMAS:\n' + [...new Set(problems)].join('\n')); process.exitCode = 1; } else console.log('Sin errores de consola ni scroll horizontal.');
