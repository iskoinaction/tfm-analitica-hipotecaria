// Recorre el flujo del Asesor (/hipotecas): paso 1 -> 2 -> 3 -> resultado, y validación vacía.
const { chromium } = require('playwright');
const OUT = process.argv[2] || './screenshots';
const BASE = 'http://127.0.0.1:8101';
(async () => {
  const browser = await chromium.launch();
  for (const [w, h, tag] of [[1440, 900, 'desktop'], [390, 844, 'mobile']]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    const dialogs = []; const errs = []; page.on('pageerror', e => errs.push(String(e).slice(0,160))); page.on('console', m => { if (m.type()==='error') errs.push(m.text().slice(0,160)); });
    page.on('dialog', async d => { dialogs.push(d.message()); await d.dismiss(); });
    await page.goto(BASE + '/login');
    await page.fill('#username', 'demo'); await page.fill('#password', 'demo');
    await Promise.all([page.waitForNavigation(), page.click('button[type=submit]')]);
    await page.goto(BASE + '/hipotecas', { waitUntil: 'load', timeout: 120000 }); await page.waitForTimeout(3000);
    // 1) clic sin año -> alert nativo
    await page.click('text=Ver analisis');
    await page.waitForTimeout(500);
    const years = await page.$$eval('#yearSelect option', os => os.map(o => o.value).filter(Boolean));
    console.log('years', years.join(','));
    await page.selectOption('#yearSelect', '2024');
    let t0 = Date.now();
    await page.click('text=Ver analisis');
    await page.waitForSelector('#step2:not(.hidden)', { timeout: 120000 });
    await page.waitForTimeout(3000);
    console.log('context ms', Date.now() - t0);
    await page.screenshot({ path: `${OUT}/asesor_paso2_${tag}.png`, fullPage: true });
    await page.click('#cardFijo');
    await page.waitForTimeout(800);
    // 2) envío sin provincia
    await page.click('text=Obtener tipo personalizado');
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${OUT}/asesor_validacion_${tag}.png`, fullPage: false });
    await page.fill('#income', '2500'); await page.fill('#savings', '40000'); await page.fill('#age', '32');
    const provs = await page.$$eval('#provinceSel option', os => os.map(o => o.value).filter(Boolean));
    await page.selectOption('#provinceSel', provs.includes('Madrid') ? 'Madrid' : provs[0]);
    t0 = Date.now();
    await page.click('text=Obtener tipo personalizado');
    // v1: el endpoint devuelve HTTP 500 (shap expected_value) y la UI se queda en el spinner; se espera 20 s
    try { await page.waitForFunction(() => !document.querySelector('#resultContent .spinner') && document.querySelector('#resultContent').innerText.length > 50, null, { timeout: 20000 }); }
    catch (e) { console.log(tag, 'RESULTADO NO LLEGA (spinner indefinido)'); }
    await page.waitForTimeout(1000);
    console.log('recomendacion ms', Date.now() - t0);
    await page.screenshot({ path: `${OUT}/asesor_resultado_${tag}.png`, fullPage: true });
    if (tag === 'desktop') {
      const t = await page.$('#gestorToggle');
      if (t) { await page.evaluate(() => { const el = document.getElementById('gestorToggle'); el.checked = true; el.dispatchEvent(new Event('change')); });
        await page.waitForTimeout(1500);
        await page.screenshot({ path: `${OUT}/asesor_modo_gestor_${tag}.png`, fullPage: true }); }
      require('fs').writeFileSync(`${OUT}/../asesor_result_text.txt`, await page.innerText('#stepResult'));
    }
    const sw = await page.evaluate(() => document.documentElement.scrollWidth);
    console.log(tag, 'scrollWidth', sw, 'dialogs', JSON.stringify(dialogs), 'errors', JSON.stringify(errs));
    await ctx.close();
  }
  await browser.close();
})();
