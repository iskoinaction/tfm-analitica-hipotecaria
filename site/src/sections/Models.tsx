import { useMemo, useState } from 'react';
import { useApp } from '../App';
import { slotFile, slotIndex, useJSON, type ArtifactItem, type Table } from '../lib/data';
import { fmtNum, fmtPeriod, humanize, periodValue } from '../lib/format';
import { Card, DataTable, JsonView, Loading, Pending, Section, SourceLine, Tabs, Field } from '../components/ui';
import { BarChart, LineChart, type Series } from '../components/charts';

type Obj = Record<string, unknown>;
const findKey = (o: Obj | undefined, prefix: string) => o && Object.keys(o).find((k) => k === prefix || k.startsWith(prefix + ' ') || k.startsWith(prefix + '('));
const get = (o: Obj | undefined, prefix: string) => { const k = findKey(o, prefix); return k ? (o![k] as Obj) : undefined; };
const SHOCK: Record<string, string> = { coste_construccion: 'Coste de construcción', euribor: 'Euríbor 12M', pib_pc: 'PIB per cápita', precio: 'Precio de la vivienda', hipotecas: 'Hipotecas (propio)' };
const pFmt = (p: unknown) => (typeof p === 'number' ? (p < 0.001 ? '< 0,001' : fmtNum(p, 3)) : '—');

function useArtifacts(domain: string) {
  const { manifest } = useApp();
  return useJSON<ArtifactItem[]>(slotIndex(manifest, 'artifacts:' + domain));
}

// ───────────────────────── Econometría ─────────────────────────
export function Econometrics() {
  const { manifest } = useApp();
  const idx = useArtifacts('econometrics');
  const items = idx.data ?? [];
  const mainJson = items.find((i) => /econometrics.*\.json$/i.test(i.name) && i.file);
  const main = useJSON<Obj>(mainJson?.file);
  const irfItem = items.find((i) => /^irf.*\.csv$/i.test(i.name) && i.file);
  const fevdItem = items.find((i) => /^fevd.*\.csv$/i.test(i.name) && i.file);
  const urItem = items.find((i) => /unit_root.*\.csv$/i.test(i.name) && i.file);
  const imgs = items.filter((i) => /\.(png|svg|jpe?g|webp)$/i.test(i.name) && i.file);
  const [tab, setTab] = useState<'var' | 'raices' | 'coint' | 'lp' | 'irf' | 'fevd' | 'diag'>('var');
  const d = main.data;
  const meta = d?.metadatos as Obj | undefined;
  const decision = d?.decision as Obj | undefined;

  return (
    <Section id="econometria" num={7} kicker="Modelos estructurales" title="Econometría"
      lead="Dinámica conjunta entre hipotecas, precio, renta, Euríbor y costes de construcción. Modelo principal: VAR en diferencias. El VECM (rango contrastado por bootstrap) se presenta como análisis de sensibilidad porque la cointegración no es concluyente, y el panel provincial como complemento exploratorio.">
      {idx.loading ? <Loading /> : !mainJson ? (
        <Pending what="Resultados econométricos" expected={['artifacts/econometrics/*.json', 'artifacts/econometrics/irf_*.csv']} />
      ) : !d ? <Loading /> : (
        <>
          <div className="grid-2 grid-2--even">
            <Card title="Modelo seleccionado" className="card--accent" source={<>Fuente: <code>{mainJson.source}</code></>}>
              <p className="kpi__value kpi__value--sm">{String(decision?.modelo_principal ?? '—')}</p>
              <p className="small">{String(decision?.regla ?? '')}</p>
              <dl className="dl mt-2">
                <dt>p-valor bootstrap (H₀: r = 0)</dt><dd>{pFmt(decision?.p_bootstrap_r0)}</dd>
                <dt>Sensibilidad</dt><dd>{String(decision?.modelo_sensibilidad ?? '—')}</dd>
                <dt>Muestra</dt><dd>{Array.isArray(meta?.muestra) ? (meta!.muestra as string[]).map(fmtPeriod).join(' – ') : '—'} {meta?.T ? `(T = ${meta.T})` : ''}</dd>
                <dt>Variables</dt><dd>{Array.isArray(meta?.variables) ? (meta!.variables as string[]).join(', ') : '—'}</dd>
              </dl>
            </Card>
            <Card title="Cómo leer estos resultados" className="card--flat">
              {typeof meta?.advertencia === 'string' && <div className="callout callout--warn small">{meta.advertencia}</div>}
              <ul className="small mt-4">
                <li>Coeficientes de largo plazo: semielasticidades/elasticidades del vector de cointegración normalizado; no son efectos causales.</li>
                <li>Las respuestas a impulso dependen de la identificación (Cholesky con un orden dado, o generalizadas); se muestran ambas con bandas bootstrap p5–p95.</li>
                <li>Diagnósticos (autocorrelación, normalidad) se publican junto a los resultados para valorar su fiabilidad.</li>
              </ul>
            </Card>
          </div>
          {decision && !/^VECM/i.test(String(decision.modelo_principal)) && (
            <div className="callout callout--warn"><strong>Conclusión honesta.</strong> Con la regla de decisión del proyecto (bootstrap salvaje, H₀: r = 0, p = {pFmt(decision.p_bootstrap_r0)} frente a un umbral de {fmtNum(Number(decision.umbral) * 100, 0)} %) <strong>no hay evidencia robusta de cointegración</strong>. El modelo principal es el {String(decision.modelo_principal)}; el VECM y los coeficientes de largo plazo se muestran solo como sensibilidad y no deben leerse como relaciones de equilibrio estables.</div>
          )}
          <Tabs label="Resultados econométricos" value={tab} onChange={setTab} tabs={[
            { id: 'var', label: 'VAR en diferencias' }, { id: 'coint', label: 'Cointegración' }, { id: 'lp', label: 'VECM (sensibilidad)' }, { id: 'irf', label: 'Impulso-respuesta' },
            { id: 'fevd', label: 'Descomposición (FEVD)' }, { id: 'raices', label: 'Raíces unitarias' }, { id: 'diag', label: 'Diagnóstico' },
          ]} />
          <div role="tabpanel">
            {tab === 'var' && <VarDiff d={d} />}
            {tab === 'coint' && <Cointegration d={d} />}
            {tab === 'lp' && <LongRun d={d} />}
            {tab === 'irf' && (irfItem ? <IrfPanel file={irfItem.file!} source={irfItem.source} /> : <Pending what="IRF" expected={['artifacts/econometrics/irf_hipotecas.csv']} />)}
            {tab === 'fevd' && (fevdItem ? <FevdPanel file={fevdItem.file!} source={fevdItem.source} /> : <Pending what="FEVD" expected={['artifacts/econometrics/fevd_hipotecas.csv']} />)}
            {tab === 'raices' && <UnitRoots d={d} file={urItem?.file} source={urItem?.source} />}
            {tab === 'diag' && <Card title="Diagnósticos de residuos y robustez"><JsonView data={{ VECM: (d.VECM as Obj)?.diagnosticos, VAR_diferencias: (d.VAR_diferencias as Obj)?.diagnosticos, ARDL_bounds: d.ARDL_bounds, panel: d.panel }} /></Card>}
          </div>
          {imgs.length > 0 && (
            <div className="gallery">
              {imgs.map((i) => <figure key={i.name}><img src={i.file} alt={`Figura ${humanize(i.name.replace(/\.\w+$/, ''))}`} loading="lazy" /><figcaption>{i.source}</figcaption></figure>)}
            </div>
          )}
        </>
      )}
      <p className="xs muted"><SourceLine manifest={manifest} slots={['artifacts:econometrics']} /></p>
    </Section>
  );
}

function VarDiff({ d }: { d: Obj }) {
  const v = d.VAR_diferencias as Obj | undefined;
  const f = v?.fevd_crecimiento_hipotecas_h20_cholesky_pct as Record<string, number> | undefined;
  const esp = v?.especificacion as Obj | undefined;
  return (
    <div className="grid-2 grid-2--even">
      <Card title="Descomposición de la varianza del crecimiento de hipotecas (h = 20, Cholesky)" subtitle="Porcentaje de la varianza del error de predicción atribuido a cada shock">
        {f ? <BarChart ariaLabel="Cuota de varianza del crecimiento de hipotecas por shock" format={(x) => fmtNum(x, 1) + ' %'} rows={Object.entries(f).map(([k, x]) => ({ label: SHOCK[k] ?? k, value: x, highlight: k === 'hipotecas' }))} /> : <Pending what="FEVD" expected={['VAR_diferencias.fevd_crecimiento_hipotecas_h20_cholesky_pct']} />}
        <p className="xs muted mt-2">La mayor parte de la varianza es propia (inercia); los demás shocks aportan cuotas moderadas y dependen del orden de identificación.</p>
      </Card>
      <Card title="Especificación y estabilidad">
        <dl className="dl">
          <dt>Retardos en diferencias (p)</dt><dd>{String(esp?.p_diferencias ?? '—')}</dd>
          <dt>T efectiva</dt><dd>{String(esp?.T_efectiva ?? '—')}</dd>
          <dt>Sistema estable</dt><dd>{v?.estable === true ? 'sí' : v?.estable === false ? 'no' : '—'}</dd>
          <dt>Raíz máxima (módulo)</dt><dd>{typeof v?.raiz_max === 'number' ? fmtNum(v.raiz_max as number, 3) : '—'}</dd>
        </dl>
        <p className="small mt-2">{String(esp?.regla_p ?? '')}</p>
      </Card>
    </div>
  );
}

function Cointegration({ d }: { d: Obj }) {
  const rp = d.rango_principal as Obj | undefined;
  const tests = (rp?.tests as Obj[]) ?? [];
  const sel = rp?.rango_seleccionado as Obj | undefined;
  return (
    <div className="grid-2">
      <Card title="Contraste de Johansen (traza)" subtitle={`Caso determinista ${rp?.case ?? '—'} · k_ar_diff = ${rp?.k_ar_diff ?? '—'} · T efectiva = ${rp?.T_efectiva ?? '—'} · bootstrap B = ${rp?.B ?? '—'}`}>
        <DataTable table={{ columns: ['H₀', 'Traza', 'Traza (Reinsel-Ahn)', 'VC 95 %', 'p bootstrap'], rows: tests.map((t) => [String(t.H0), t.trace as number, t.trace_reinsel_ahn as number, t.cv95_trace as number, pFmt(t.p_bootstrap_trace)]) }} />
        {tests.length > 0 && <BarChart ariaLabel="Estadístico de traza por hipótesis frente al valor crítico" rows={tests.map((t) => ({ label: `H₀: ${t.H0}`, value: t.trace as number, highlight: (t.trace as number) > (t.cv95_trace as number) }))} format={(v) => fmtNum(v, 1)} />}
        <p className="xs muted">Barras naranjas: la traza supera el valor crítico asintótico al 95 %.</p>
      </Card>
      <Card title="Rango seleccionado según criterio">
        {sel ? <dl className="dl">{Object.entries(sel).map(([k, v]) => <FragmentDl key={k} k={humanize(k)} v={String(v)} />)}</dl> : '—'}
        <p className="small mt-4">La decisión usa el bootstrap (más fiable en muestras cortas) frente a los valores críticos asintóticos, que tienden a sobrerrechazar.</p>
      </Card>
    </div>
  );
}
function FragmentDl({ k, v }: { k: string; v: string }) { return <><dt>{k}</dt><dd>{v}</dd></>; }

function LongRun({ d }: { d: Obj }) {
  const vecm = d.VECM as Obj | undefined;
  const beta = get(vecm, 'beta_normalizado_hipotecas');
  const alpha = get(vecm, 'alpha_normalizado_hipotecas');
  const rows = (o?: Obj, field = 'coef_LP') => Object.entries(o ?? {}).map(([k, v]) => [SHOCK[k] ?? k, (v as Obj)[field] as number, (v as Obj).se as number, pFmt((v as Obj).p)]);
  return (
    <div className="grid-2 grid-2--even">
      <Card title="Vector de cointegración (normalizado en log hipotecas)" subtitle="Coeficientes de largo plazo con error estándar">
        <DataTable table={{ columns: ['Variable', 'Coeficiente', 'Error est.', 'p'], rows: rows(beta) }} />
        {typeof vecm?.euribor_semielasticidad_hipotecas_pct_por_pp === 'number' && (
          <p className="small mt-2">Semielasticidad implícita del Euríbor: <strong className="num">{fmtNum(vecm.euribor_semielasticidad_hipotecas_pct_por_pp as number, 1)} %</strong> por punto porcentual (según el signo del vector normalizado; interpretar junto a la tabla y a la advertencia de identificación).</p>
        )}
      </Card>
      <Card title="Velocidades de ajuste (α)" subtitle="Respuesta de cada variable al desequilibrio de largo plazo">
        <DataTable table={{ columns: ['Ecuación', 'α', 'Error est.', 'p'], rows: rows(alpha, 'alpha') }} />
        {typeof vecm?.semivida_ECT_sistema_trimestres === 'number' && <p className="small mt-2">Semivida del término de corrección del sistema: <strong className="num">{fmtNum(vecm.semivida_ECT_sistema_trimestres as number, 1)}</strong> trimestres.</p>}
      </Card>
    </div>
  );
}

function UnitRoots({ d, file, source }: { d: Obj; file?: string; source?: string }) {
  const dict = d.raices_unitarias_dictamen as Obj | undefined;
  const t = useJSON<Table>(file);
  return (
    <div className="stack">
      <Card title="Orden de integración (dictamen)">
        <DataTable table={{ columns: ['Serie', 'Dictamen'], rows: Object.entries(dict ?? {}).map(([k, v]) => [k, String(v)]) }} />
      </Card>
      {t.data && <Card title="Contrastes detallados (ADF, DF-GLS, PP, KPSS, Zivot-Andrews)" source={source && <>Fuente: <code>{source}</code></>}><DataTable table={t.data} maxRows={12} /></Card>}
    </div>
  );
}

function IrfPanel({ file, source }: { file: string; source: string }) {
  const t = useJSON<Table>(file);
  const models = useMemo(() => t.data ? [...new Set(t.data.rows.map((r) => String(r[t.data!.columns.indexOf('modelo')])))] : [], [t.data]);
  const idents = useMemo(() => t.data ? [...new Set(t.data.rows.map((r) => String(r[t.data!.columns.indexOf('identificacion')])))] : [], [t.data]);
  const [model, setModel] = useState(''); const [ident, setIdent] = useState('');
  if (!t.data) return <Loading />;
  const c = (n: string) => t.data!.columns.indexOf(n);
  const m = model || models[0], id = ident || idents[0];
  const rows = t.data.rows.filter((r) => r[c('modelo')] === m && r[c('identificacion')] === id);
  const shocks = [...new Set(rows.map((r) => String(r[c('shock')])))];
  return (
    <Card title="Respuesta de las hipotecas a un shock de una desviación típica" subtitle="Log-puntos (≈ variación relativa) por horizonte en trimestres; banda bootstrap p5–p95"
      source={<>Fuente: <code>{source}</code></>}>
      <div className="controls">
        <Field id="irf-model" label="Modelo"><select id="irf-model" className="select" value={m} onChange={(e) => setModel(e.target.value)}>{models.map((x) => <option key={x}>{x}</option>)}</select></Field>
        <Field id="irf-id" label="Identificación"><select id="irf-id" className="select" value={id} onChange={(e) => setIdent(e.target.value)}>{idents.map((x) => <option key={x}>{x}</option>)}</select></Field>
      </div>
      <div className="grid-2 grid-2--even">
        {shocks.map((s) => {
          const pts = rows.filter((r) => r[c('shock')] === s).map((r) => ({ x: r[c('horizonte')] as number, y: r[c('valor')] as number, lo: r[c('p5')] as number, hi: r[c('p95')] as number }));
          const ser: Series[] = [{ name: SHOCK[s] ?? s, color: 'var(--series-1)', points: pts }];
          return (
            <div key={s}>
              <p className="kpi__label">Shock: {SHOCK[s] ?? s}</p>
              <LineChart series={ser} height={200} xFormat={(x) => `h${x}`} yFormat={(v) => fmtNum(v, 3)} ariaLabel={`Respuesta de hipotecas a shock de ${SHOCK[s] ?? s}`} />
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function FevdPanel({ file, source }: { file: string; source: string }) {
  const t = useJSON<Table>(file);
  const [h, setH] = useState<number | null>(null);
  const [method, setMethod] = useState('');
  if (!t.data) return <Loading />;
  const c = (n: string) => t.data!.columns.indexOf(n);
  const models = [...new Set(t.data.rows.map((r) => String(r[c('modelo')])))];
  const methods = [...new Set(t.data.rows.map((r) => String(r[c('metodo')])))];
  const hs = [...new Set(t.data.rows.map((r) => r[c('horizonte')] as number))].sort((a, b) => a - b);
  const hh = h ?? hs[hs.length - 1], mm = method || methods[0];
  const rows = t.data.rows.filter((r) => r[c('modelo')] === models[0] && r[c('metodo')] === mm && r[c('horizonte')] === hh);
  return (
    <Card title={`Descomposición de la varianza del error de predicción de las hipotecas (${models[0]})`} subtitle="Porcentaje atribuido a cada shock, con intervalo bootstrap p5–p95" source={<>Fuente: <code>{source}</code></>}>
      <div className="controls">
        <Field id="fevd-h" label="Horizonte (trimestres)"><select id="fevd-h" className="select" value={hh} onChange={(e) => setH(Number(e.target.value))}>{hs.map((x) => <option key={x} value={x}>{x}</option>)}</select></Field>
        <Field id="fevd-m" label="Método"><select id="fevd-m" className="select" value={mm} onChange={(e) => setMethod(e.target.value)}>{methods.map((x) => <option key={x}>{x}</option>)}</select></Field>
      </div>
      <BarChart ariaLabel="Cuota de la varianza por shock" unit="%" format={(v) => fmtNum(v, 1) + ' %'}
        rows={rows.map((r) => ({ label: SHOCK[String(r[c('shock')])] ?? String(r[c('shock')]), value: r[c('cuota_pct')] as number, lo: r[c('p5_pct')] as number, hi: r[c('p95_pct')] as number }))} />
    </Card>
  );
}

// ───────────────────────── Machine Learning ─────────────────────────
const BENCH = new Set(['naive', 'seasonal_naive', 'media_movil_4']);
const MODEL_LABEL: Record<string, string> = { elasticnet: 'Elastic net', random_forest: 'Random forest', lightgbm: 'LightGBM', gbm: 'Gradient boosting', xgboost: 'XGBoost', drift: 'Deriva (drift)', naive: 'Persistencia (naive)', seasonal_naive: 'Estacional ingenuo', media_movil_4: 'Media móvil 4T', ets_log: 'ETS (log)', sarima_log: 'SARIMA (log)', ar_log: 'AR (log)', lightgbm_pooled: 'LightGBM (panel)', condicional_ex_post: 'Condicional ex post (oráculo)', condicional_cap1: 'Condicional OLS (ΔEuríbor, Δparo)', condicional_cap2: 'Condicional OLS cap. 2', condicional_cap4: 'Condicional OLS cap. 4' };
const mLabel = (m: string) => MODEL_LABEL[m] ?? humanize(m);

export function MachineLearning() {
  const { manifest } = useApp();
  const dIdx = useArtifacts('demand');
  const fIdx = useArtifacts('forecasting');
  const files = (dIdx.data ?? []).filter((i) => i.file && /nacional_metricas\.(csv|json)$/.test(i.name));
  const metaItem = (dIdx.data ?? []).find((i) => i.name === 'metadata.json' && i.file);
  const fMeta = (fIdx.data ?? []).find((i) => i.name === 'metadata.json' && i.file);
  const meta = useJSON<any>(metaItem?.file); // eslint-disable-line @typescript-eslint/no-explicit-any
  const macro = useJSON<any>(fMeta?.file); // eslint-disable-line @typescript-eslint/no-explicit-any
  const [serie, setSerie] = useState('');
  const [win, setWin] = useState('holdout');
  const [metric, setMetric] = useState('MASE');
  const cur = files.find((f) => f.name === serie) ?? files.find((f) => /viviendas/.test(f.name)) ?? files[0];
  const tbl = useJSON<Table>(cur?.file);
  const dmItem = (dIdx.data ?? []).find((i) => cur && i.name === cur.name.replace('_metricas', '_dm') && i.file);
  const dm = useJSON<Table>(dmItem?.file);
  const hs: number[] = meta.data?.protocolo?.horizontes_tabla ?? [1, 2, 4, 8];
  const key = cur ? (cur.name.includes('total_fincas') ? 'hipotecas_total_fincas' : 'hipotecas_viviendas') : 'hipotecas_viviendas';
  const selH = (meta.data?.demanda?.[key]?.seleccionado_por_h ?? {}) as Record<string, string>;

  const pivot = useMemo(() => {
    const t = tbl.data; if (!t) return null;
    const c = (n: string) => t.columns.indexOf(n);
    const rows = t.rows.filter((r) => r[c('window')] === win && hs.includes(Number(r[c('h')])));
    const models = [...new Set(rows.map((r) => String(r[c('model')])))];
    const val = (m: string, h: number) => rows.find((r) => r[c('model')] === m && Number(r[c('h')]) === h)?.[c(metric)] as number | undefined;
    const bestPerH = hs.map((h) => { let b: string | null = null; for (const m of models) { const v = val(m, h); if (v != null && (b == null || v < val(b, h)!)) b = m; } return b; });
    const bench = hs.map((h) => Math.min(...models.filter((m) => BENCH.has(m)).map((m) => val(m, h) ?? Infinity)));
    return { models: models.sort((a, b) => Number(BENCH.has(b)) - Number(BENCH.has(a)) || (val(a, hs[0]) ?? 9e9) - (val(b, hs[0]) ?? 9e9)), val, bestPerH, bench, n: rows.find((r) => Number(r[c('h')]) === hs[0]) ? rows.find((r) => Number(r[c('h')]) === hs[0])![c('n')] : null };
  }, [tbl.data, win, metric, hs]);

  return (
    <Section id="ml" num={8} kicker="Predicción" title="Machine Learning"
      lead="Los modelos se comparan con referencias ingenuas (persistencia, estacional, media móvil) mediante validación rolling-origin: en cada origen solo se usa la información disponible entonces. Se elige por horizonte con la ventana de selección y se evalúa una única vez en el hold-out.">
      {dIdx.loading || meta.loading ? <Loading /> : !files.length ? (
        <Pending what="Benchmark rolling-origin" expected={['artifacts/demand/*_nacional_metricas.csv']} />
      ) : (
        <>
          <Card title="Error por horizonte frente a benchmarks (rolling-origin)" subtitle={`Protocolo: primer origen ${meta.data?.protocolo?.primer_origen ?? '—'}, selección hasta ${meta.data?.protocolo?.fin_seleccion ?? '—'}, hold-out ${(meta.data?.protocolo?.holdout ?? []).join(' – ')}`}
            source={<SourceLine manifest={manifest} slots={['artifacts:demand']} extra={cur && <code>{cur.source}</code>} />}>
            <div className="controls">
              <Field id="ml-serie" label="Serie"><select id="ml-serie" className="select" value={cur?.name ?? ''} onChange={(e) => setSerie(e.target.value)}>{files.map((f) => <option key={f.name} value={f.name}>{/total_fincas/.test(f.name) ? 'Hipotecas, total fincas (nacional)' : 'Hipotecas sobre viviendas (nacional)'}</option>)}</select></Field>
              <Field id="ml-win" label="Ventana"><select id="ml-win" className="select" value={win} onChange={(e) => setWin(e.target.value)}><option value="holdout">Hold-out (evaluación única)</option><option value="seleccion">Selección</option><option value="oos_extra">Fuera de muestra extra</option></select></Field>
              <Field id="ml-met" label="Métrica"><select id="ml-met" className="select" value={metric} onChange={(e) => setMetric(e.target.value)}>{['MASE', 'MAPE', 'RMSE', 'MAE', 'TheilU'].map((m) => <option key={m}>{m}</option>)}</select></Field>
            </div>
            {pivot ? (
              <div className="table-wrap" tabIndex={0} role="region" aria-label="Tabla rolling-origin por horizonte">
                <table className="table table--compact">
                  <caption>{metric} por modelo y horizonte (trimestres){pivot.n ? ` · n = ${pivot.n} orígenes en h = ${hs[0]}` : ''}. Negrita: mejor por horizonte. Filas con etiqueta «benchmark»: referencias ingenuas.</caption>
                  <thead><tr><th scope="col">Modelo</th>{hs.map((h) => <th key={h} scope="col" className="num">h = {h}</th>)}</tr></thead>
                  <tbody>{pivot.models.map((m) => (
                    <tr key={m}><th scope="row" style={{ fontWeight: 500 }}>{mLabel(m)} {BENCH.has(m) && <span className="badge badge--neutral">benchmark</span>}{hs.some((h) => selH[String(h)] === m) && <span className="badge badge--info">seleccionado h={hs.filter((h) => selH[String(h)] === m).join(',')}</span>}</th>
                      {hs.map((h, i) => { const v = pivot.val(m, h); return <td key={h} className="num" style={pivot.bestPerH[i] === m ? { fontWeight: 700, background: 'var(--brand-accent-soft)' } : undefined}>{v == null ? '—' : fmtNum(v, metric === 'MAPE' || metric === 'MASE' || metric === 'TheilU' ? 2 : 0)}{metric === 'MAPE' ? ' %' : ''}</td>; })}</tr>))}</tbody>
                </table>
              </div>
            ) : <Loading />}
            {metric === 'MASE' && <p className="xs muted mt-2">MASE &lt; 1: mejor que la persistencia en el periodo de entrenamiento. Theil U &lt; 1: mejor que la persistencia en la ventana evaluada.</p>}
          </Card>
          <div className="grid-2 grid-2--even">
            <Card title="Contraste Diebold-Mariano" subtitle="Modelo frente a benchmark; p-valor de pérdida cuadrática (muestras cortas: potencia limitada)">
              {dm.data ? <DataTable maxRows={12} table={{ columns: ['h', 'Ventana', 'Modelo', 'Benchmark', 'n', 'DM', 'p'], rows: (() => { const c = (n: string) => dm.data!.columns.indexOf(n); const seen = new Set<string>(); return dm.data!.rows.filter((r) => { const k = [r[c('h')], r[c('window')], r[c('model')], r[c('benchmark')]].join('|'); if (seen.has(k)) return false; seen.add(k); return true; }).map((r) => [r[c('h')], r[c('window')], mLabel(String(r[c('model')])), mLabel(String(r[c('benchmark')])), r[c('n')], r[c('DM_sq')], pFmt(r[c('p_sq')])]); })() }} format={(v) => (typeof v === 'number' ? fmtNum(v, Number.isInteger(v) ? 0 : 2) : String(v ?? '—'))} /> : <Loading />}
            </Card>
            <Card title="Variables macro: modelo seleccionado" subtitle="Menor MASE de selección por variable (panel provincial)">
              {macro.data?.macro ? <DataTable table={{ columns: ['Variable', 'Seleccionado', 'MASE sel.', 'MASE persistencia'], rows: Object.entries(macro.data.macro as Obj).map(([k, v]) => { const sc = (v as Obj).score_seleccion_MASE as Record<string, number>; const s = String((v as Obj).seleccionado); return [humanize(k), mLabel(s), sc?.[s] ?? null, sc?.naive ?? null]; }) }} format={(v) => (typeof v === 'number' ? fmtNum(v, 2) : String(v ?? '—'))} /> : <Pending what="Selección macro" expected={['artifacts/forecasting/metadata.json']} />}
            </Card>
          </div>
        </>
      )}
      <div className="callout small">Regla de publicación: un modelo solo se presenta como mejor que la referencia si su error es menor de forma consistente por horizonte (y, cuando se publica, con contraste Diebold-Mariano). Si no la mejora, se dice. El «condicional ex post» usa el valor realizado de las variables explicativas y es solo un techo de referencia, no una predicción.</div>
    </Section>
  );
}

export function GenericArtifact({ item }: { item: ArtifactItem }) {
  const d = useJSON<unknown>(item.file);
  return (
    <Card title={item.name} source={<>Fuente: <code>{item.source}</code></>}>
      {d.loading ? <Loading /> : (d.data as Table)?.columns ? <DataTable table={d.data as Table} maxRows={20} /> : <JsonView data={d.data} />}
    </Card>
  );
}

// ───────────────────────── Predicciones y escenarios ─────────────────────────
interface ScenarioBlock { definicion?: string; base?: Record<string, number>; sensibilidades?: Record<string, Record<string, number>>; observado_trimestral?: Record<string, number>; nota?: string; metodo_base?: string }

function keyToX(k: string): number | null {
  const v = periodValue(k);
  if (/^\d{4}$/.test(k)) return Number(k) + 0.375; // media anual: centro del año
  return Number.isFinite(v) ? v : null;
}
function applySens(base: Record<string, number>, sens: Record<string, number> | undefined): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [k, v] of Object.entries(base)) {
    let d = 0;
    if (sens) {
      if (k in sens) d = sens[k];
      else {
        const desde = Object.entries(sens).filter(([s]) => s.startsWith('desde_')).map(([s, x]) => [Number(s.slice(6)), x] as const).filter(([y]) => Number(k.slice(0, 4)) >= y).sort((a, b) => b[0] - a[0])[0];
        if (desde) d = desde[1];
      }
    }
    out[k] = v + d;
  }
  return out;
}

function MacroAssumptions() {
  const { manifest } = useApp();
  const sc = useJSON<Obj>(slotFile(manifest, 'escenarios'));
  const nat = useJSON<Table>(slotFile(manifest, 'nacional_trimestral'));
  const blocks = Object.entries(sc.data ?? {}).filter(([, v]) => v && typeof v === 'object' && (v as ScenarioBlock).base) as [string, ScenarioBlock][];
  const [var_, setVar] = useState('euribor_12m');
  const block = blocks.find(([k]) => k === var_)?.[1] ?? blocks[0]?.[1];
  const key = blocks.find(([k]) => k === var_)?.[0] ?? blocks[0]?.[0];
  const natCol: Record<string, string> = { euribor_12m: 'euribor_12m', paro_nacional: 'tasa_paro', ipc_espana: 'ipc_var_anual' };
  const series: Series[] = [];
  if (block?.base && key) {
    const obsCol = natCol[key];
    if (obsCol && nat.data) {
      const i = nat.data.columns.indexOf(obsCol), ip = nat.data.columns.indexOf('period');
      series.push({ name: 'Observado (trimestral)', color: 'var(--series-1)', points: nat.data.rows.filter((r) => periodValue(String(r[ip])) >= 2015).map((r) => ({ x: periodValue(String(r[ip])), y: r[i] as number | null })) });
    }
    const mk = (name: string, vals: Record<string, number>, color: string, dashed = true) => series.push({ name, color, dashed, points: Object.entries(vals).map(([k, v]) => ({ x: keyToX(k)!, y: v })).filter((p) => p.x != null).sort((a, b) => a.x - b.x) });
    mk('Escenario base', block.base, 'var(--series-2)');
    if (block.sensibilidades?.adverso) mk('Sensibilidad adversa', applySens(block.base, block.sensibilidades.adverso), 'var(--series-8)');
    if (block.sensibilidades?.favorable) mk('Sensibilidad favorable', applySens(block.base, block.sensibilidades.favorable), 'var(--series-3)');
  }
  const fuentes = (sc.data?.fuentes ?? {}) as Record<string, Obj>;
  const lastObs = series[0]?.points.filter((p) => p.y != null).at(-1)?.x;
  return (
    <>
      {sc.loading ? <Loading /> : !blocks.length ? <Pending what="Escenarios macro" expected={['data/metadata/escenarios_macro.yaml']} /> : (
        <div className="grid-2">
          <Card title="Supuestos macroeconómicos" subtitle={`Versión ${String(sc.data?.version ?? '—')} · corte de información ${String(sc.data?.fecha_corte_informacion ?? '—')}`}
            source={<SourceLine manifest={manifest} slots={['escenarios', 'nacional_trimestral']} />}>
            <div className="controls">
              <Field id="sc-var" label="Variable">
                <select id="sc-var" className="select" value={key} onChange={(e) => setVar(e.target.value)}>
                  {blocks.map(([k]) => <option key={k} value={k}>{humanize(k)}</option>)}
                </select>
              </Field>
            </div>
            <LineChart series={series} height={280} xFormat={(x) => String(Math.floor(x))} yFormat={(v) => fmtNum(v, 1)} markerX={lastObs} markerLabel="último dato"
              ariaLabel={`Observado y escenarios para ${humanize(key ?? '')}`} />
            {block?.definicion && <p className="xs muted mt-2">{block.definicion}</p>}
          </Card>
          <Card title="Valores del escenario" subtitle="Base y sensibilidades (puntos sobre la base). Las sensibilidades son supuestos propios, no escenarios institucionales.">
            {block?.base && (
              <DataTable table={{
                columns: ['Periodo', 'Base', 'Adversa', 'Favorable'],
                rows: Object.keys(block.base).map((k) => [fmtPeriod(k), block.base![k], block.sensibilidades?.adverso ? applySens(block.base!, block.sensibilidades.adverso)[k] : null, block.sensibilidades?.favorable ? applySens(block.base!, block.sensibilidades.favorable)[k] : null]),
              }} format={(v) => (typeof v === 'number' ? fmtNum(v, 2) : String(v ?? '—'))} />
            )}
            {(block?.metodo_base || block?.nota) && <p className="xs muted mt-2">{block.metodo_base ?? block.nota}</p>}
            <details className="mt-4"><summary className="small">Fuentes de los supuestos</summary>
              <ul className="xs">{Object.entries(fuentes).map(([k, f]) => <li key={k}><strong>{String(f.nombre ?? k)}</strong>{f.url != null && <> · <a href={String(f.url).split(' ')[0]} target="_blank" rel="noopener noreferrer">enlace</a></>} · consultado {String(f.consultado ?? '—')}</li>)}</ul>
            </details>
          </Card>
        </div>
      )}
    </>
  );
}


// Proyecciones 2026-2030 (data/forecasts/*.csv): provincia, prov_code, period, variable, escenario, valor, p10, p90, modelo
const FC_OBS: Record<string, { panel?: string; nat?: string; annual?: boolean; unit: string; label: string }> = {
  hipotecas_viviendas: { panel: 'hipotecas_viviendas_num', nat: 'hipotecas_viviendas_num', unit: 'hipotecas / trimestre', label: 'Hipotecas sobre viviendas' },
  hipotecas_total_fincas: { panel: 'hipotecas_fincas_total_num', nat: 'hipotecas_fincas_total_num', unit: 'hipotecas / trimestre', label: 'Hipotecas, total fincas' },
  compraventas_viviendas: { panel: 'compraventas_viviendas_num', nat: 'compraventas_viviendas_num', unit: 'compraventas / trimestre', label: 'Compraventas de viviendas' },
  precio_m2_mivau: { panel: 'precio_m2_mivau_tasado', nat: 'precio_m2_mivau_tasado', unit: '€/m² (MIVAU, valor tasado)', label: 'Precio m² (MIVAU)' },
  tasa_paro: { panel: 'tasa_paro', nat: 'tasa_paro', unit: '%', label: 'Tasa de paro' },
  euribor_12m: { nat: 'euribor_12m', unit: '%', label: 'Euríbor 12M (escenario)' },
  pib_pc: { panel: 'pib_pc', annual: true, unit: '€ por habitante', label: 'PIB per cápita' },
  poblacion: { panel: 'poblacion', annual: true, unit: 'personas', label: 'Población' },
  poblacion_extranjera: { panel: 'poblacion_extranjera', annual: true, unit: 'personas', label: 'Población extranjera' },
};
const pc = (x: unknown) => String(x ?? '').padStart(2, '0');
const SC_STYLE: Record<string, { color: string; name: string }> = { base: { color: 'var(--series-2)', name: 'Escenario base' }, adverso: { color: 'var(--series-8)', name: 'Adverso' }, favorable: { color: 'var(--series-3)', name: 'Favorable' }, referencia_naive: { color: 'var(--series-7)', name: 'Referencia naive' } };

export function Forecasts() {
  const { manifest } = useApp();
  const fidx = useJSON<{ name: string; source: string; file: string }[]>(slotIndex(manifest, 'forecasts'));
  const item = (fidx.data ?? []).find((f) => /proyecciones.*\.json$/i.test(f.file) && !/summary/i.test(f.name));
  const sumItem = (fidx.data ?? []).find((f) => /summary/i.test(f.name));
  const fc = useJSON<Table>(item?.file);
  const summary = useJSON<Obj>(sumItem?.file);
  const nat = useJSON<Table>(slotFile(manifest, 'nacional_trimestral'));
  const [v, setV] = useState('hipotecas_viviendas');
  const [terr, setTerr] = useState('00');
  const info = FC_OBS[v] ?? { unit: '', label: humanize(v) };
  const obsPanel = useJSON<Record<string, Record<string, number>>>(info.panel && terr !== '00' ? `data/panel/${info.annual ? 'panel_anual' : 'panel_trimestral'}/${info.panel}.json` : null);

  const cols = fc.data?.columns ?? [];
  const c = (n: string) => cols.indexOf(n);
  const vars = useMemo(() => [...new Set((fc.data?.rows ?? []).map((r) => String(r[c('variable')])))], [fc.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const rowsV = useMemo(() => (fc.data?.rows ?? []).filter((r) => r[c('variable')] === v), [fc.data, v]); // eslint-disable-line react-hooks/exhaustive-deps
  const terrs = useMemo(() => { const m = new Map<string, string>(); rowsV.forEach((r) => m.set(pc(r[c('prov_code')]), String(r[c('provincia')]))); return [...m.entries()].sort((a, b) => (a[0] === '00' ? -1 : b[0] === '00' ? 1 : a[1].localeCompare(b[1], 'es'))); }, [rowsV]); // eslint-disable-line react-hooks/exhaustive-deps
  const terrOk = terrs.some(([k]) => k === terr) ? terr : terrs[0]?.[0] ?? '00';
  const rows = rowsV.filter((r) => pc(r[c('prov_code')]) === terrOk);
  const scens = [...new Set(rows.map((r) => String(r[c('escenario')])))];
  const xOf = (p: string) => (/^\d{4}$/.test(p) ? Number(p) + 0.375 : periodValue(p));

  const series: Series[] = [];
  let obs: { x: number; y: number | null }[] = [];
  if (terrOk === '00' && info.nat && nat.data) {
    const i = nat.data.columns.indexOf(info.nat), ip = nat.data.columns.indexOf('period');
    if (i >= 0) obs = nat.data.rows.map((r) => ({ x: periodValue(String(r[ip])), y: typeof r[i] === 'number' ? (r[i] as number) : null }));
  } else if (obsPanel.data) {
    obs = Object.entries(obsPanel.data).map(([p, o]) => ({ x: xOf(p), y: o[terrOk] ?? null }));
  }
  obs = obs.filter((p) => Number.isFinite(p.x) && p.x >= 2012).sort((a, b) => a.x - b.x);
  if (obs.length) series.push({ name: 'Observado', color: 'var(--series-1)', points: obs, band: false });
  for (const s of scens) {
    const st = SC_STYLE[s] ?? { color: 'var(--series-4)', name: s };
    const pts = rows.filter((r) => r[c('escenario')] === s).map((r) => ({ x: xOf(String(r[c('period')])), y: r[c('valor')] as number, lo: r[c('p10')] as number | null, hi: r[c('p90')] as number | null })).sort((a, b) => a.x - b.x);
    series.push({ name: st.name, color: st.color, dashed: true, points: pts, band: s === 'base' });
  }
  const lastObs = obs.filter((p) => p.y != null).at(-1)?.x;
  const lastP = [...new Set(rows.map((r) => String(r[c('period')])))].sort((a, b) => xOf(a) - xOf(b)).at(-1);
  const end = rows.filter((r) => String(r[c('period')]) === lastP);
  const fmtY = (x: number) => fmtNum(x, Math.abs(x) >= 100 ? 0 : 1);

  return (
    <Section id="predicciones" num={9} kicker="Horizonte 2030" title="Predicciones y escenarios 2030"
      lead="Las proyecciones son condicionales a supuestos macroeconómicos versionados, con fuente y fecha. Se muestran con intervalos empíricos p10–p90 del backtest y escenarios adverso/favorable; nunca como cifra única.">
      {fc.loading || fidx.loading ? <Loading /> : !fc.data ? (
        <Pending what="Proyecciones 2026-2030 con intervalos" expected={['data/forecasts/proyecciones_*.csv']} />
      ) : (
        <Card title={`${info.label} · ${terrs.find(([k]) => k === terrOk)?.[1] ?? ''}`} subtitle={`Unidad: ${info.unit}. Línea continua: observado; discontinua: proyección; banda: intervalo p10–p90 del escenario base.`}
          source={<SourceLine manifest={manifest} slots={['forecasts']} extra={summary.data?.filas ? `${fmtNum(summary.data.filas as number, 0)} filas` : undefined} />}>
          <div className="controls">
            <Field id="fc-var" label="Variable"><select id="fc-var" className="select" value={v} onChange={(e) => setV(e.target.value)}>{vars.map((x) => <option key={x} value={x}>{FC_OBS[x]?.label ?? humanize(x)}</option>)}</select></Field>
            <Field id="fc-terr" label="Ámbito"><select id="fc-terr" className="select" value={terrOk} onChange={(e) => setTerr(e.target.value)}>{terrs.map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select></Field>
          </div>
          <LineChart series={series} height={300} xFormat={(x) => String(Math.floor(x + 1e-9))} yFormat={fmtY} markerX={lastObs} markerLabel="último dato"
            ariaLabel={`Observado y proyección de ${info.label}, ${terrs.find(([k]) => k === terrOk)?.[1] ?? ''}, con escenarios e intervalos`} />
          <div className="mt-4"><DataTable table={{ columns: ['Escenario', `Valor ${lastP ? fmtPeriod(lastP) : ''}`, 'p10', 'p90', 'Método'], rows: end.map((r) => [SC_STYLE[String(r[c('escenario')])]?.name ?? String(r[c('escenario')]), r[c('valor')], r[c('p10')], r[c('p90')], String(r[c('modelo')])]) }} format={(x) => (typeof x === 'number' ? fmtNum(x, Math.abs(x) >= 100 ? 0 : 2) : String(x ?? '—'))} /></div>
          <p className="xs muted mt-2">Los intervalos son cuantiles empíricos del error de backtest, no garantizan cobertura. Los escenarios adverso/favorable son sensibilidades de supuestos, no predicciones.</p>
        </Card>
      )}
      <MacroAssumptions />
    </Section>
  );
}
