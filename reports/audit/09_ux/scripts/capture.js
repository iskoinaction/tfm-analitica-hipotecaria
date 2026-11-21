// Captura de pantallas de la app v1 (Flask en :8101) a 1440px y 390px, DPR 1.
// Uso: NODE_PATH=/opt/node22/lib/node_modules node capture.js <outdir>
const { chromium } = require('playwright');
const OUT = process.argv[2] || './screenshots';
const BASE = 'http://127.0.0.1:8101';
const PAGES = [
  ['login', '/login', false],
  ['dashboard', '/', true],
  ['business_case', '/business_case', true],
  ['test_hipoteca', '/test-hipoteca', true],
  ['hipotecas', '/hipotecas', true],
  ['hipotecas_provincial', '/hipotecas-provincial', true],
  ['demanda', '/demanda', true],
  ['demanda_provincial', '/demanda-provincial', true],
  ['econometria', '/econometria', true],
  ['vecm', '/vecm', true],
  ['metodologia_ml', '/metodologia-ml', true],
  ['webscrapping', '/webscrapping', true],
];
(async () => {
  const browser = await chromium.launch();
  const report = [];
  for (const [w, h, tag] of [[1440, 900, 'desktop'], [390, 844, 'mobile']]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    const errors = [];
    page.on('console', m => { if (m.type() === 'error') errors.push(m.text().slice(0, 200)); });
    page.on('pageerror', e => errors.push('pageerror: ' + String(e).slice(0, 200)));
    await page.goto(BASE + '/login');
    await page.fill('#username', 'demo'); await page.fill('#password', 'demo');
    await Promise.all([page.waitForNavigation(), page.click('button[type=submit]')]);
    await page.goto(BASE + '/logout'); // to capture login page itself first
    for (const [name, path, auth] of PAGES) {
      if (auth && name === 'dashboard') {
        await page.goto(BASE + '/login');
        await page.fill('#username', 'demo'); await page.fill('#password', 'demo');
        await Promise.all([page.waitForNavigation(), page.click('button[type=submit]')]);
      }
      errors.length = 0;
      const t0 = Date.now();
      let status = null;
      try {
        const resp = await page.goto(BASE + path, { waitUntil: 'networkidle', timeout: 90000 });
        status = resp && resp.status();
      } catch (e) { errors.push('goto: ' + e.message.slice(0, 120)); }
      await page.waitForTimeout(2500);
      const ms = Date.now() - t0;
      const metrics = await page.evaluate(() => ({
        scrollW: document.documentElement.scrollWidth,
        clientW: document.documentElement.clientWidth,
        height: document.documentElement.scrollHeight,
        imgsNoAlt: [...document.images].filter(i => !i.hasAttribute('alt')).length,
        h1: [...document.querySelectorAll('h1')].map(e => e.textContent.trim().slice(0, 80)),
        canvases: document.querySelectorAll('canvas').length,
        inputsNoLabel: [...document.querySelectorAll('input,select,textarea')].filter(el => {
          if (el.type === 'hidden') return false;
          if (el.getAttribute('aria-label') || el.getAttribute('aria-labelledby')) return false;
          if (el.id && document.querySelector(`label[for="${el.id}"]`)) return false;
          if (el.closest('label')) return false; return true;
        }).length,
        ariaCount: document.querySelectorAll('[aria-label],[role],[aria-live]').length,
        mainLandmark: !!document.querySelector('main'),
      }));
      const file = `${OUT}/${name}_${tag}.png`;
      await page.screenshot({ path: file, fullPage: true, type: 'png' });
      report.push({ name, tag, status, ms, ...metrics, errors: [...new Set(errors)].slice(0, 5) });
      console.log(name, tag, status, ms + 'ms', JSON.stringify(metrics));
    }
    await ctx.close();
  }
  require('fs').writeFileSync(`${OUT}/../capture_metrics.json`, JSON.stringify(report, null, 2));
  await browser.close();
})();
