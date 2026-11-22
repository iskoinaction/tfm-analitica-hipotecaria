#!/usr/bin/env node
/**
 * sync-data.mjs — Copia y reduce los datos REALES del repositorio a site/public/data/.
 *
 * Lee (relativo a la raíz del repo, el directorio padre de site/):
 *   artifacts/**            resultados de modelos y controles de calidad (JSON/CSV/figuras)
 *   data/metadata/**        catálogo de fuentes, diccionario, escenarios, política del simulador, fiscalidad
 *   data/processed/*.csv    panel maestro v2 (se reduce a un JSON por variable)
 *   data/forecasts/**       proyecciones 2026-2030 (CSV → JSON)
 *   docs/**                 índice de documentación técnica (solo rutas, no contenido)
 *   Web/static/spain-provinces.geojson (o data/metadata/geo/*.geojson) → GeoJSON simplificado
 *
 * No inventa nada: si un fichero no existe, el "slot" queda como `pending` y la web lo muestra así.
 * Si el directorio padre no está disponible (p. ej. despliegue sin el repo completo) conserva el
 * contenido previo de public/data/ y termina sin error.
 *
 * Uso: node scripts/sync-data.mjs [--verbose]
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { execSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import yaml from 'js-yaml';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SITE = path.resolve(__dirname, '..');
const ROOT = path.resolve(SITE, '..');
const OUT = path.join(SITE, 'public', 'data');
const VERBOSE = process.argv.includes('--verbose');

const LIMITS = {
  jsonBytes: 3 * 1024 * 1024,   // JSON copiado tal cual
  csvRows: 20000,               // filas máximas por CSV convertido
  imageBytes: 1.5 * 1024 * 1024,
  images: 12,
};
const SKIP_DIRS = new Set(['inputs', 'cache', 'boe_cache', '__pycache__', 'tmp', '.ipynb_checkpoints']);

const log = (...a) => console.log('[sync-data]', ...a);
const vlog = (...a) => VERBOSE && log(...a);
const rel = (p) => path.relative(ROOT, p).split(path.sep).join('/');
const exists = (p) => { try { fs.accessSync(p); return true; } catch { return false; } };

function walk(dir, { exts, maxDepth = 6 } = {}, depth = 0) {
  if (!exists(dir) || depth > maxDepth) return [];
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (e.name.startsWith('.')) continue;
    const p = path.join(dir, e.name);
    if (e.isDirectory()) {
      if (SKIP_DIRS.has(e.name)) continue;
      out.push(...walk(p, { exts, maxDepth }, depth + 1));
    } else if (!exts || exts.includes(path.extname(e.name).toLowerCase())) out.push(p);
  }
  return out.sort();
}

function writeJSON(relOut, obj) {
  const p = path.join(OUT, relOut);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(obj));
  return 'data/' + relOut.split(path.sep).join('/');
}

function sha256(p) { return crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex').slice(0, 16); }
function mtime(p) { return fs.statSync(p).mtime.toISOString(); }

// ───────────── CSV ─────────────
function parseCSV(text) {
  const rows = [];
  let row = [], field = '', q = false;
  const sep = (() => { const first = text.split(/\r?\n/, 1)[0] || ''; return (first.split(';').length > first.split(',').length) ? ';' : ','; })();
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else q = false; }
      else field += c;
    } else if (c === '"') q = true;
    else if (c === sep) { row.push(field); field = ''; }
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++;
      row.push(field); field = '';
      if (row.length > 1 || row[0] !== '') rows.push(row);
      row = [];
    } else field += c;
  }
  if (field !== '' || row.length) { row.push(field); rows.push(row); }
  return rows;
}
const NUM_RE = /^-?\d+(\.\d+)?([eE][-+]?\d+)?$/;
function coerce(v) {
  if (v === '' || v == null) return null;
  const t = v.trim();
  if (NUM_RE.test(t)) return Number(t);
  if (/^(nan|NaN|NA|null|None)$/.test(t)) return null;
  if (t === 'True' || t === 'true') return true;
  if (t === 'False' || t === 'false') return false;
  return t;
}
function csvToTable(p, maxRows = LIMITS.csvRows) {
  const rows = parseCSV(fs.readFileSync(p, 'utf8').replace(/^﻿/, ''));
  const columns = rows.shift() || [];
  const truncated = rows.length > maxRows;
  return { columns, rows: rows.slice(0, maxRows).map((r) => r.map(coerce)), n_rows: rows.length, truncated };
}

// ───────────── Slots ─────────────
const manifest = {
  generated_at: new Date().toISOString(),
  repo_commit: null,
  root_available: false,
  slots: {},
};
function slot(key, data) { manifest.slots[key] = { status: 'pending', files: [], sources: [], ...data }; }

function gitCommit() {
  try { return execSync('git rev-parse --short HEAD', { cwd: ROOT, stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim(); }
  catch { return null; }
}

// 1) Metadatos (YAML/CSV/JSON) → JSON
function syncMetadata() {
  const dir = path.join(ROOT, 'data', 'metadata');
  const files = walk(dir, { exts: ['.yaml', '.yml', '.json', '.csv'], maxDepth: 2 });
  const index = [];
  for (const f of files) {
    const base = rel(f).replace(/^data\/metadata\//, '');
    if (base.startsWith('manifests/')) continue; // se tratan aparte
    let content;
    try {
      const ext = path.extname(f).toLowerCase();
      if (ext === '.csv') content = csvToTable(f);
      else if (ext === '.json') content = JSON.parse(fs.readFileSync(f, 'utf8'));
      else content = yaml.load(fs.readFileSync(f, 'utf8'));
    } catch (e) { log('AVISO no se pudo leer', rel(f), e.message); continue; }
    const out = writeJSON(path.join('metadata', base.replace(/\.(ya?ml|csv|json)$/i, '.json')), content);
    index.push({ name: base, source: rel(f), file: out, updated: mtime(f), sha256: sha256(f) });
  }
  // manifests de ejecución del pipeline (solo los 10 más recientes)
  const manifests = walk(path.join(dir, 'manifests'), { exts: ['.json'] })
    .sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs).slice(0, 10);
  const runs = [];
  for (const f of manifests) {
    try { runs.push({ source: rel(f), updated: mtime(f), file: writeJSON(path.join('metadata', 'manifests', path.basename(f)), JSON.parse(fs.readFileSync(f, 'utf8'))) }); }
    catch (e) { log('AVISO manifest ilegible', rel(f), e.message); }
  }
  const find = (re) => index.find((x) => re.test(x.name));
  const mk = (key, title, re) => {
    const hit = find(re);
    slot(key, { title, ...(hit ? { status: 'ok', files: [hit.file], sources: [hit.source], updated: hit.updated } : {}) });
  };
  mk('sources', 'Catálogo de fuentes', /^(sources|series_catalog)\.(ya?ml|json)$/i);
  mk('variables', 'Diccionario de variables', /^(variables|data_dictionary)\.(ya?ml|json|csv)$/i);
  mk('provenance', 'Procedencia de los snapshots', /^provenance\.(csv|json)$/i);
  mk('aranceles', 'Aranceles notarial y registral', /^aranceles\.(ya?ml|json)$/i);
  mk('availability', 'Reglas de disponibilidad', /^availability_rules\.(ya?ml|json)$/i);
  mk('provincias', 'Provincias (códigos INE)', /^provincias\.(csv|ya?ml|json)$/i);
  mk('escenarios', 'Escenarios macro', /^escenarios_macro\.(ya?ml|json)$/i);
  mk('advisor_policy', 'Política del simulador', /^advisor_policy\.(ya?ml|json)$/i);
  mk('fiscalidad', 'Tabla fiscal con vigencias', /^fiscalidad(_vigencias)?\.(csv|ya?ml|json)$/i);
  slot('metadata_index', { title: 'Metadatos', status: index.length ? 'ok' : 'pending', files: [writeJSON('metadata/_index.json', index)], sources: index.map((x) => x.source) });
  slot('pipeline_runs', { title: 'Ejecuciones del pipeline', status: runs.length ? 'ok' : 'pending', files: [writeJSON('metadata/_runs.json', runs)], sources: runs.map((r) => r.source), updated: runs[0]?.updated });
}

// 2) Artefactos por dominio
function syncArtifacts() {
  const base = path.join(ROOT, 'artifacts');
  const domains = exists(base) ? fs.readdirSync(base, { withFileTypes: true }).filter((d) => d.isDirectory()).map((d) => d.name) : [];
  const all = {};
  for (const d of ['data_quality', 'econometrics', 'forecasting', 'demand', 'advisor', 'economics', 'figures', ...domains]) {
    if (all[d]) continue;
    const dir = path.join(base, d);
    const files = walk(dir, { exts: ['.json', '.csv', '.png', '.svg', '.jpg', '.jpeg', '.webp', '.md'] });
    const items = [];
    let images = 0;
    for (const f of files) {
      const ext = path.extname(f).toLowerCase();
      const name = path.relative(dir, f).split(path.sep).join('/');
      const size = fs.statSync(f).size;
      const item = { name, source: rel(f), updated: mtime(f), bytes: size, kind: ext.slice(1) };
      try {
        if (ext === '.json') {
          if (size > LIMITS.jsonBytes) { item.skipped = 'demasiado grande'; items.push(item); continue; }
          item.file = writeJSON(path.join('artifacts', d, name), JSON.parse(fs.readFileSync(f, 'utf8')));
        } else if (ext === '.csv') {
          const t = csvToTable(f);
          item.file = writeJSON(path.join('artifacts', d, name.replace(/\.csv$/i, '.json')), t);
          item.n_rows = t.n_rows; item.truncated = t.truncated;
        } else if (ext === '.md') {
          const p = path.join(OUT, 'artifacts', d, name);
          fs.mkdirSync(path.dirname(p), { recursive: true }); fs.copyFileSync(f, p);
          item.file = 'data/' + path.join('artifacts', d, name).split(path.sep).join('/');
        } else {
          if (size > LIMITS.imageBytes || images >= LIMITS.images) { item.skipped = 'imagen omitida por tamaño/cantidad'; items.push(item); continue; }
          const p = path.join(OUT, 'artifacts', d, name);
          fs.mkdirSync(path.dirname(p), { recursive: true }); fs.copyFileSync(f, p);
          item.file = 'data/' + path.join('artifacts', d, name).split(path.sep).join('/');
          images++;
        }
      } catch (e) { item.error = e.message; log('AVISO', rel(f), e.message); }
      items.push(item);
    }
    all[d] = items;
    const ok = items.filter((i) => i.file);
    slot('artifacts:' + d, {
      title: 'artifacts/' + d,
      status: ok.length ? 'ok' : 'pending',
      files: [writeJSON(path.join('artifacts', d, '_index.json'), items)],
      sources: items.map((i) => i.source),
      updated: ok.map((i) => i.updated).sort().at(-1),
    });
  }
}

// 3) Panel procesado → JSON por variable
function syncPanel() {
  const candidates = ['panel_trimestral.csv', 'panel_anual.csv'];
  for (const name of candidates) {
    const f = path.join(ROOT, 'data', 'processed', name);
    const key = name.startsWith('panel_trimestral') ? 'panel_trimestral' : 'panel_anual';
    if (!exists(f)) {
      const pq = f.replace(/\.csv$/, '.parquet');
      slot(key, { title: name, note: exists(pq) ? 'Solo existe la versión .parquet; exporte también a CSV para la web.' : undefined });
      continue;
    }
    const t = csvToTable(f, Infinity);
    const col = (re) => t.columns.findIndex((c) => re.test(c));
    const iProv = col(/^(prov_code|cod_prov|provincia_code)$/i);
    const iPer = col(/^(period|periodo|trimestre|year|anio|año)$/i);
    const iName = col(/^(prov_name|provincia|nombre)$/i);
    if (iProv < 0 || iPer < 0) { slot(key, { title: name, note: 'No se encontraron columnas prov_code/period', sources: [rel(f)] }); continue; }
    const skip = new Set([iProv, iPer, iName, col(/^(ccaa|ccaa_code|ccaa_name|geo_level|is_projection|freq)$/i)].filter((i) => i >= 0));
    const numericCols = t.columns.map((c, i) => i).filter((i) => !skip.has(i) && t.rows.some((r) => typeof r[i] === 'number'));
    const periods = [...new Set(t.rows.map((r) => String(r[iPer])))].sort();
    const provinces = {};
    for (const r of t.rows) {
      const code = String(r[iProv]).padStart(2, '0');
      if (!provinces[code]) provinces[code] = iName >= 0 ? String(r[iName]) : code;
    }
    const vars = [];
    for (const i of numericCols) {
      const v = t.columns[i];
      const byPeriod = {};
      let n = 0;
      for (const r of t.rows) {
        const val = r[i];
        if (typeof val !== 'number' || !Number.isFinite(val)) continue;
        const p = String(r[iPer]); const code = String(r[iProv]).padStart(2, '0');
        (byPeriod[p] ||= {})[code] = Number(val.toPrecision(6));
        n++;
      }
      const safe = v.replace(/[^A-Za-z0-9_-]/g, '_');
      // ¿la variable varía entre provincias en algún periodo? Si no, es nacional replicada (no apta para mapa)
      const provincial = Object.values(byPeriod).some((o) => new Set(Object.values(o)).size > 1);
      vars.push({ key: v, file: writeJSON(path.join('panel', key, safe + '.json'), byPeriod), n_values: n, scope: provincial ? 'provincial' : 'nacional' });
    }
    slot(key, {
      title: name, status: 'ok', sources: [rel(f)], updated: mtime(f),
      files: [writeJSON(path.join('panel', key, '_index.json'), { periods, provinces, variables: vars, n_rows: t.n_rows, sha256: sha256(f) })],
    });
  }
}

// 3b) Serie nacional trimestral (tabla completa, es pequeña)
function syncNacional() {
  const f = path.join(ROOT, 'data', 'processed', 'nacional_trimestral.csv');
  if (!exists(f)) { slot('nacional_trimestral', { title: 'nacional_trimestral.csv' }); return; }
  slot('nacional_trimestral', { title: 'nacional_trimestral.csv', status: 'ok', sources: [rel(f)], updated: mtime(f), files: [writeJSON('panel/nacional_trimestral.json', csvToTable(f, Infinity))] });
}

// 4) Proyecciones
function syncForecasts() {
  const dir = path.join(ROOT, 'data', 'forecasts');
  const files = walk(dir, { exts: ['.csv', '.json'] });
  const items = [];
  for (const f of files) {
    const name = path.relative(dir, f).split(path.sep).join('/');
    try {
      const out = f.endsWith('.csv')
        ? writeJSON(path.join('forecasts', name.replace(/\.csv$/i, '.json')), csvToTable(f))
        : writeJSON(path.join('forecasts', name), JSON.parse(fs.readFileSync(f, 'utf8')));
      items.push({ name, source: rel(f), updated: mtime(f), file: out });
    } catch (e) { log('AVISO', rel(f), e.message); }
  }
  const parquet = walk(dir, { exts: ['.parquet'] });
  slot('forecasts', {
    title: 'data/forecasts', status: items.length ? 'ok' : 'pending',
    files: [writeJSON('forecasts/_index.json', items)], sources: items.map((i) => i.source),
    updated: items.map((i) => i.updated).sort().at(-1),
    note: !items.length && parquet.length ? `Hay ${parquet.length} fichero(s) .parquet sin CSV equivalente.` : undefined,
  });
}

// 5) GeoJSON provincial simplificado (Douglas-Peucker + redondeo + descarte de islotes)
function rdp(pts, eps) {
  if (pts.length < 3) return pts;
  const [x1, y1] = pts[0]; const [x2, y2] = pts[pts.length - 1];
  const dx = x2 - x1, dy = y2 - y1; const n = Math.hypot(dx, dy) || 1e-12;
  let dmax = 0, idx = 0;
  for (let i = 1; i < pts.length - 1; i++) {
    const d = Math.abs(dy * pts[i][0] - dx * pts[i][1] + x2 * y1 - y2 * x1) / n;
    if (d > dmax) { dmax = d; idx = i; }
  }
  if (dmax > eps) return [...rdp(pts.slice(0, idx + 1), eps).slice(0, -1), ...rdp(pts.slice(idx), eps)];
  return [pts[0], pts[pts.length - 1]];
}
function simplifyRing(r, eps, nd) {
  let s;
  if (r.length > 4) { const m = Math.floor(r.length / 2); s = [...rdp(r.slice(0, m + 1), eps).slice(0, -1), ...rdp(r.slice(m), eps)]; }
  else s = r;
  if (s.length < 4) s = r;
  const f = 10 ** nd;
  const out = s.map(([x, y]) => [Math.round(x * f) / f, Math.round(y * f) / f]);
  if (out[0][0] !== out.at(-1)[0] || out[0][1] !== out.at(-1)[1]) out.push(out[0]);
  return out;
}
const ringArea = (r) => Math.abs(r.slice(0, -1).reduce((a, p, i) => a + p[0] * r[i + 1][1] - r[i + 1][0] * p[1], 0)) / 2;
function syncGeo() {
  const cands = [
    ...walk(path.join(ROOT, 'data', 'metadata', 'geo'), { exts: ['.geojson', '.json'] }),
    path.join(ROOT, 'Web', 'static', 'spain-provinces.geojson'),
    path.join(ROOT, 'Web', 'static', 'data', 'spain-provinces.geojson'),
  ].filter(exists);
  if (!cands.length) { slot('geo', { title: 'GeoJSON provincial' }); return; }
  const src = cands[0];
  const g = JSON.parse(fs.readFileSync(src, 'utf8'));
  const eps = 0.02, nd = 3, minArea = 0.005;
  const features = g.features.map((f) => {
    const polys = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates;
    const sorted = [...polys].sort((a, b) => ringArea(b[0]) - ringArea(a[0]));
    const kept = sorted.filter((pl, i) => i === 0 || ringArea(pl[0]) >= minArea);
    const p = f.properties || {};
    const code = String(p.cod_prov ?? p.prov_code ?? p.codigo ?? '').padStart(2, '0');
    return {
      type: 'Feature',
      properties: { prov_code: code, name: p.name ?? p.nombre ?? code, ccaa_code: p.cod_ccaa != null ? String(p.cod_ccaa).padStart(2, '0') : null },
      geometry: { type: 'MultiPolygon', coordinates: kept.map((pl) => pl.map((r) => simplifyRing(r, eps, nd))) },
    };
  });
  const file = writeJSON('geo/provincias.json', { type: 'FeatureCollection', features });
  slot('geo', {
    title: 'GeoJSON provincial simplificado', status: 'ok', files: [file], sources: [rel(src)], updated: mtime(src),
    note: `Simplificado: Douglas-Peucker ${eps}°, ${nd} decimales, islotes < ${minArea} grados² descartados; ${features.length} provincias.`,
  });
}

// 6) Documentación técnica
function syncDocs() {
  const files = walk(path.join(ROOT, 'docs'), { exts: ['.md', '.pdf', '.html', '.ipynb'] , maxDepth: 3 });
  const items = files.map((f) => {
    let title = path.basename(f);
    if (f.endsWith('.md')) {
      const h = fs.readFileSync(f, 'utf8').split(/\r?\n/).find((l) => /^#\s+/.test(l));
      if (h) title = h.replace(/^#\s+/, '').trim();
    }
    return { path: rel(f), title, updated: mtime(f), bytes: fs.statSync(f).size };
  });
  const readme = exists(path.join(ROOT, 'README.md')) ? [{ path: 'README.md', title: 'README del repositorio', updated: mtime(path.join(ROOT, 'README.md')) }] : [];
  slot('docs', { title: 'docs/', status: items.length ? 'ok' : 'pending', files: [writeJSON('docs/_index.json', [...items, ...readme])], sources: items.map((i) => i.path) });
}

// 7) Capturas de la aplicación bancaria v2
function syncAppScreens() {
  const dirs = ['docs/screenshots/app', 'docs/screenshots', 'Web/docs/screenshots', 'reports/audit/07_software/screenshots'];
  let files = [];
  let from = null;
  for (const d of dirs) {
    const f = walk(path.join(ROOT, d), { exts: ['.png', '.jpg', '.jpeg', '.webp'], maxDepth: 1 }).filter((p) => fs.statSync(p).size <= LIMITS.imageBytes);
    if (f.length) { files = f.slice(0, LIMITS.images); from = d; break; }
  }
  const items = files.map((f) => {
    const p = path.join(OUT, 'app', path.basename(f));
    fs.mkdirSync(path.dirname(p), { recursive: true }); fs.copyFileSync(f, p);
    return { name: path.basename(f), source: rel(f), file: 'data/app/' + path.basename(f), updated: mtime(f) };
  });
  slot('app_screens', { title: 'Capturas de la app v2', status: items.length ? 'ok' : 'pending', files: [writeJSON('app/_index.json', items)], sources: items.map((i) => i.source), note: from ? `Origen: ${from}` : undefined });
}

// ───────────── main ─────────────
function main() {
  if (!exists(path.join(ROOT, 'artifacts')) && !exists(path.join(ROOT, 'data')) && !exists(path.join(ROOT, 'Web'))) {
    log('Repositorio padre no disponible: se conserva public/data/ existente.');
    return;
  }
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(OUT, { recursive: true });
  manifest.root_available = true;
  manifest.repo_commit = gitCommit();
  syncMetadata();
  syncArtifacts();
  syncPanel();
  syncNacional();
  syncForecasts();
  syncGeo();
  syncDocs();
  syncAppScreens();
  writeJSON('manifest.json', manifest);
  const ok = Object.entries(manifest.slots).filter(([, s]) => s.status === 'ok').map(([k]) => k);
  const pend = Object.entries(manifest.slots).filter(([, s]) => s.status !== 'ok').map(([k]) => k);
  log(`OK (${ok.length}): ${ok.join(', ') || '—'}`);
  log(`Pendientes (${pend.length}): ${pend.join(', ') || '—'}`);
  vlog(JSON.stringify(manifest, null, 2));
}
main();
