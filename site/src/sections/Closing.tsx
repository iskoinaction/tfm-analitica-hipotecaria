import { useApp } from '../App';
import { artifactFile, slotFile, slotIndex, useJSON, type ArtifactItem, type Table } from '../lib/data';
import { fmtDate, fmtNum, humanize } from '../lib/format';
import { Card, Pending, Section, Loading } from '../components/ui';

type Obj = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const env = import.meta.env as Record<string, string | undefined>;
const APP_URL = env.VITE_APP_URL || '';

export function BankApp() {
  const { manifest } = useApp();
  const shots = useJSON<{ name: string; file: string }[]>(slotFile(manifest, 'app_screens') ?? slotIndex(manifest, 'app_screens'));
  const list = shots.data ?? [];
  return (
    <Section id="app" num={11} kicker="Producto" title="Aplicación bancaria"
      lead="La aplicación web (Flask) consume los mismos artefactos que esta presentación: panel provincial, demanda, proyecciones y el simulador hipotecario. Esta web no sustituye a la aplicación.">
      <div className="row">
        {APP_URL ? <a className="btn btn--primary" href={APP_URL} target="_blank" rel="noopener noreferrer">Abrir la aplicación ↗</a>
          : <span className="badge badge--neutral">Enlace a la aplicación no configurado (variable <code>VITE_APP_URL</code>)</span>}
      </div>
      {list.length ? (
        <div className="gallery">{list.map((s) => <figure key={s.name}><img src={s.file} alt={`Captura de la aplicación: ${humanize(s.name.replace(/\.\w+$/, ''))}`} loading="lazy" /><figcaption>{s.name}</figcaption></figure>)}</div>
      ) : <Pending what="Capturas de la aplicación" expected={['Web/docs/screenshots/*.png|jpg']} note="Las capturas se copian automáticamente al sincronizar cuando existan en el repositorio." />}
      <div className="callout small">Ejecución local: <code>pip install -r Web/requirements.txt</code> y <code>python Web/wsgi.py</code> (ver <code>Web/README.md</code>).</div>
    </Section>
  );
}

export function Results() {
  const { manifest } = useApp();
  const econ = useJSON<Obj>(artifactFile(useJSON<ArtifactItem[]>(slotIndex(manifest, 'artifacts:econometrics')).data, /^econometrics_v2\.json$/)?.file);
  const dIdx = useJSON<ArtifactItem[]>(slotIndex(manifest, 'artifacts:demand'));
  const met = useJSON<Table>(artifactFile(dIdx.data, /^hipotecas_viviendas_nacional_metricas\.(csv|json)$/)?.file);
  const meta = useJSON<Obj>(artifactFile(dIdx.data, /^metadata\.json$/)?.file);
  const fc = useJSON<Table>(useJSON<{ name: string; file: string }[]>(slotIndex(manifest, 'forecasts')).data?.find((x) => /\.csv|proyecciones.*\.json$/i.test(x.name) && !/summary/.test(x.name))?.file);

  // Hold-out: modelo seleccionado frente al mejor benchmark, por horizonte (datos reales)
  const rows: { h: number; sel: string; bench: string; mSel: number; mBench: number }[] = [];
  const m = met.data, sel = meta.data?.demanda?.hipotecas_viviendas?.seleccionado_por_h as Record<string, string> | undefined, best = meta.data?.demanda?.hipotecas_viviendas?.mejor_benchmark_por_h as Record<string, string> | undefined;
  if (m && sel && best) {
    const c = (n: string) => m.columns.indexOf(n);
    for (const h of Object.keys(sel)) {
      const g = (mod: string) => m.rows.find((r) => r[c('model')] === mod && String(r[c('h')]) === h && r[c('window')] === 'holdout')?.[c('MASE')] as number | undefined;
      const a = g(sel[h]), b = g(best[h]);
      if (a != null && b != null) rows.push({ h: Number(h), sel: sel[h], bench: best[h], mSel: a, mBench: b });
    }
  }
  const dec = econ.data?.decision as Obj | undefined;
  const end = fc.data ? (() => {
    const c = (n: string) => fc.data!.columns.indexOf(n);
    const r = fc.data!.rows.filter((x) => x[c('variable')] === 'hipotecas_viviendas' && Number(x[c('prov_code')]) === 0 && x[c('escenario')] === 'base' && String(x[c('period')]).startsWith('2030'));
    return r.length ? { v: r.reduce((a, x) => a + (x[c('valor')] as number), 0), lo: r.reduce((a, x) => a + (x[c('p10')] as number), 0), hi: r.reduce((a, x) => a + (x[c('p90')] as number), 0), n: r.length } : null;
  })() : null;

  return (
    <Section id="resultados" num={12} kicker="Síntesis" title="Resultados y conclusiones"
      lead="Conclusiones tal y como las respaldan los artefactos publicados; donde un resultado es negativo o no concluyente, se dice.">
      {econ.loading || met.loading ? <Loading /> : (
        <div className="feature-grid">
          <Card title="Econometría" className="card--flat">
            {dec ? <p className="small">La regla de decisión (bootstrap, H₀: r = 0, p = {fmtNum(dec.p_bootstrap_r0 as number, 3)}) <strong>no encuentra evidencia robusta de cointegración</strong>: el modelo principal es el <strong>{String(dec.modelo_principal)}</strong> y el VECM se presenta solo como sensibilidad. Las descomposiciones de varianza son condicionales a la identificación y no prueban causalidad.</p>
              : <Pending what="Conclusión econométrica" expected={['artifacts/econometrics/econometrics_v2.json']} />}
          </Card>
          <Card title="Predicción" className="card--flat">
            {rows.length ? (<>
              <p className="small">Error MASE en el hold-out 2022T1–2025T4, modelo seleccionado frente al mejor benchmark (MASE &lt; 1 mejora a la persistencia en muestra):</p>
              <ul className="small">{rows.map((r) => <li key={r.h}>h = {r.h}: <code>{r.sel}</code> {fmtNum(r.mSel, 2)} frente a <code>{r.bench}</code> {fmtNum(r.mBench, 2)} → <strong>{r.mSel < r.mBench ? 'mejora' : 'no mejora'}</strong></li>)}</ul>
            </>) : <Pending what="Resultados de predicción" expected={['artifacts/demand/*_metricas.csv']} />}
          </Card>
          <Card title="Proyección 2030" className="card--flat">
            {end ? <p className="small">Escenario base, España, hipotecas sobre vivienda en 2030: <strong className="num">{fmtNum(end.v, 0)}</strong> en el año (suma de {end.n} trimestres; banda p10–p90 por trimestre sumada: {fmtNum(end.lo, 0)} – {fmtNum(end.hi, 0)}, indicativa). Es una proyección condicionada a supuestos, no una predicción.</p>
              : <Pending what="Proyecciones 2026–2030" expected={['data/forecasts/proyecciones_*.csv']} />}
          </Card>
          <Card title="Producto" className="card--flat">
            <p className="small">Pipeline reproducible con trazabilidad por snapshot, panel provincial v2, y un simulador determinista verificado contra el motor Python (18 casos). Precio por m²: solo MIVAU (valor tasado).</p>
          </Card>
        </div>
      )}
      <p className="xs muted">Generado {fmtDate(manifest?.generated_at, true)} a partir de los artefactos del repositorio.</p>
    </Section>
  );
}

export function Limitations() {
  const items = [
    ['Asociación, no causalidad', 'Las respuestas a impulso y la descomposición de varianza dependen de la identificación elegida; no prueban efectos causales.'],
    ['Muestra corta y rupturas', 'La muestra econométrica (≈ 86 trimestres) incluye crisis y cambios regulatorios; hay diagnósticos con rechazos (estacionalidad, rupturas).'],
    ['Sin cointegración robusta', 'El contraste bootstrap no rechaza ausencia de cointegración: el VECM es solo una sensibilidad.'],
    ['Predicción modesta', 'Frente a la persistencia, la mejora de los modelos es limitada y varía por horizonte; los intervalos son empíricos del backtest.'],
    ['Escenarios = supuestos', 'Las sendas de Euríbor y paro proceden de documentos de organismos o de sensibilidades propias; no son predicciones.'],
    ['Datos provisionales', 'Los últimos periodos del INE son provisionales y pueden revisarse; la fecha de publicación es una aproximación.'],
    ['Precio de vivienda', 'Se usa el valor tasado MIVAU (no el precio de cierre). Una serie privada previa no se publica por sus condiciones de uso.'],
    ['Simulador ilustrativo', 'Umbrales DSTI/LTV/LTI y estrés son supuestos; los impuestos no incluyen todas las bonificaciones; los aranceles son una cota inferior.'],
    ['Marca ficticia', 'Atalaya es un proyecto académico; no representa a ninguna entidad ni constituye asesoramiento o scoring.'],
  ];
  return (
    <Section id="limitaciones" num={13} kicker="Honestidad metodológica" title="Limitaciones" lead="Qué no debe inferirse de esta presentación.">
      <div className="feature-grid">{items.map(([t, d]) => <div key={t} className="card feature"><h3>{t}</h3><p>{d}</p></div>)}</div>
    </Section>
  );
}

export function Docs() {
  const { manifest } = useApp();
  const idx = useJSON<{ path: string; title: string; updated: string }[]>(slotIndex(manifest, 'docs'));
  const base = (env.VITE_REPO_URL || manifest?.repo_url || '').replace(/\/$/, '');
  const branch = env.VITE_REPO_BRANCH || manifest?.repo_branch || 'main';
  const link = (p: string) => (base ? `${base}/blob/${branch}/${p}` : null);
  const list = idx.data ?? [];
  return (
    <Section id="documentacion" num={14} kicker="Referencias" title="Documentación técnica"
      lead="Informes de auditoría, documentación del repositorio y metadatos. Los enlaces apuntan al repositorio (configurable con VITE_REPO_URL).">
      {idx.loading ? <Loading /> : !list.length ? <Pending what="Índice de documentación" expected={['docs/*.md', 'reports/audit/*.md']} /> : (
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Documentación técnica"><table className="table table--compact">
          <thead><tr><th>Documento</th><th>Ruta</th><th>Modificado</th></tr></thead>
          <tbody>{list.map((d) => { const u = link(d.path); return (
            <tr key={d.path}><td>{u ? <a href={u} target="_blank" rel="noopener noreferrer">{d.title}</a> : d.title}</td><td className="xs"><code>{d.path}</code></td><td className="xs nowrap">{fmtDate(d.updated)}</td></tr>); })}</tbody></table></div>
      )}
      {base && <p className="small">Repositorio: <a href={base} target="_blank" rel="noopener noreferrer">{base.replace('https://', '')}</a></p>}
    </Section>
  );
}
