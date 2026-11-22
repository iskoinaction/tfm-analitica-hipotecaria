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
  const [tab, setTab] = useState<'raices' | 'coint' | 'lp' | 'irf' | 'fevd' | 'antes' | 'diag'>('coint');
  const d = main.data;
  const meta = d?.metadatos as Obj | undefined;
  const decision = d?.decision as Obj | undefined;

  return (
    <Section id="econometria" num={7} kicker="Modelos estructurales" title="Econometría"
      lead="Relación de largo plazo entre hipotecas, precio, renta, Euríbor y costes de construcción (VECM con rango contrastado por bootstrap), con VAR en diferencias como sensibilidad y modelos de panel provincial.">
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
          <Tabs label="Resultados econométricos" value={tab} onChange={setTab} tabs={[
            { id: 'coint', label: 'Cointegración' }, { id: 'lp', label: 'Largo plazo' }, { id: 'irf', label: 'Impulso-respuesta' },
            { id: 'fevd', label: 'Descomposición (FEVD)' }, { id: 'raices', label: 'Raíces unitarias' }, { id: 'antes', label: 'v1 vs v2' }, { id: 'diag', label: 'Diagnóstico' },
          ]} />
          <div role="tabpanel">
            {tab === 'coint' && <Cointegration d={d} />}
            {tab === 'lp' && <LongRun d={d} />}
            {tab === 'irf' && (irfItem ? <IrfPanel file={irfItem.file!} source={irfItem.source} /> : <Pending what="IRF" expected={['artifacts/econometrics/irf_hipotecas.csv']} />)}
            {tab === 'fevd' && (fevdItem ? <FevdPanel file={fevdItem.file!} source={fevdItem.source} /> : <Pending what="FEVD" expected={['artifacts/econometrics/fevd_hipotecas.csv']} />)}
            {tab === 'raices' && <UnitRoots d={d} file={urItem?.file} source={urItem?.source} />}
            {tab === 'antes' && <BeforeAfter d={d} />}
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

function BeforeAfter({ d }: { d: Obj }) {
  const ad = d.antes_despues as Obj | undefined;
  const v1 = ad?.v1_documentado as Obj | undefined, v2 = ad?.v2_VECM as Obj | undefined;
  if (!v1 || !v2) return <JsonView data={ad} />;
  const keys = Object.keys(v2).filter((k) => k in v1);
  const val = (x: unknown) => (x && typeof x === 'object' && !Array.isArray(x) ? ((x as Obj).coef_LP ?? (x as Obj).alpha) : x) as number;
  return (
    <Card title="Versión 1 documentada frente a versión 2 reproducible" subtitle="Mismos conceptos; la v2 se estima con datos oficiales corregidos y rango contrastado por bootstrap.">
      <DataTable table={{ columns: ['Parámetro', 'v1 (documentado)', 'v2 (VECM)'], rows: keys.map((k) => [k, val(v1[k]), val(v2[k])]) }} />
      <p className="xs muted mt-2">Las diferencias de signo y magnitud reflejan la corrección de datos de la v1 (formato de miles en hipotecas, series sustituidas) y no deben leerse como cambios del mercado.</p>
    </Card>
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
export function MachineLearning() {
  const { manifest } = useApp();
  const fc = useArtifacts('forecasting');
  const dm = useArtifacts('demand');
  const items = [...(fc.data ?? []), ...(dm.data ?? [])].filter((i) => i.file && /\.(json|csv)$/i.test(i.name));
  const rolling = items.filter((i) => /rolling|backtest|benchmark/i.test(i.name));
  const others = items.filter((i) => !rolling.includes(i));
  return (
    <Section id="ml" num={8} kicker="Predicción" title="Machine Learning"
      lead="Los modelos se comparan con referencias ingenuas (persistencia, estacional) mediante validación rolling-origin: en cada origen solo se usa la información disponible entonces, y se reporta el error por horizonte.">
      {fc.loading || dm.loading ? <Loading /> : !items.length ? (
        <Pending what="Benchmark rolling-origin" expected={['artifacts/forecasting/*rolling*.csv|json', 'artifacts/forecasting/model_selection.json', 'artifacts/demand/*']} />
      ) : (
        <>
          {rolling.map((i) => <RollingTable key={i.source} item={i} />)}
          {!rolling.length && <Pending what="Tabla rolling-origin por horizonte" expected={['artifacts/forecasting/*rolling*.csv']} />}
          {others.slice(0, 6).map((i) => <GenericArtifact key={i.source} item={i} />)}
        </>
      )}
      <div className="callout small">Regla de publicación: un modelo solo se presenta como mejor que la referencia si su error es menor de forma consistente por horizonte (y, cuando se publica, con contraste Diebold-Mariano). En caso contrario se informa de que no la mejora.</div>
      <p className="xs muted"><SourceLine manifest={manifest} slots={['artifacts:forecasting', 'artifacts:demand']} /></p>
    </Section>
  );
}

function RollingTable({ item }: { item: ArtifactItem }) {
  const d = useJSON<unknown>(item.file);
  const t = useMemo(() => {
    const x = d.data as Table | Obj[] | Obj | undefined;
    if (!x) return null;
    if (Array.isArray((x as Table).columns)) return x as Table;
    const arr = Array.isArray(x) ? x : ((x as Obj).rolling ?? (x as Obj).results ?? (x as Obj).tabla) as Obj[] | undefined;
    if (!Array.isArray(arr)) return null;
    const cols = [...new Set(arr.flatMap((r) => Object.keys(r)))];
    return { columns: cols, rows: arr.map((r) => cols.map((c) => r[c] as never)) } as Table;
  }, [d.data]);
  if (d.loading) return <Loading />;
  if (!t) return <GenericArtifact item={item} />;
  const hi = t.columns.findIndex((c) => /^(h|horizon|horizonte)$/i.test(c));
  const mi = t.columns.findIndex((c) => /^(mape|mase|rmse|mae)/i.test(c));
  const best = new Set<number>();
  if (hi >= 0 && mi >= 0) {
    const byH = new Map<unknown, number>();
    t.rows.forEach((r, j) => { const cur = byH.get(r[hi]); if (typeof r[mi] === 'number' && (cur == null || (r[mi] as number) < (t.rows[cur][mi] as number))) byH.set(r[hi], j); });
    byH.forEach((j) => best.add(j));
  }
  return (
    <Card title={`Error por horizonte · ${item.name}`} subtitle={mi >= 0 ? `Resaltado: menor ${t.columns[mi]} en cada horizonte` : undefined} source={<>Fuente: <code>{item.source}</code></>}>
      <DataTable table={t} maxRows={60} highlight={(r) => best.has(t.rows.indexOf(r))} />
    </Card>
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

export function Forecasts() {
  const { manifest } = useApp();
  const sc = useJSON<Obj>(slotFile(manifest, 'escenarios'));
  const fidx = useJSON<{ name: string; source: string; file: string }[]>(slotIndex(manifest, 'forecasts'));
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
    <Section id="predicciones" num={9} kicker="Horizonte 2030" title="Predicciones y escenarios 2030"
      lead="Las proyecciones son condicionales a supuestos macroeconómicos versionados, con fuente y fecha. Se presentan con intervalos y sensibilidades, nunca como cifra única.">
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
              <ul className="xs">{Object.entries(fuentes).map(([k, f]) => <li key={k}><strong>{String(f.nombre ?? k)}</strong>{f.url && <> · <a href={String(f.url).split(' ')[0]} target="_blank" rel="noopener noreferrer">enlace</a></>} · consultado {String(f.consultado ?? '—')}</li>)}</ul>
            </details>
          </Card>
        </div>
      )}
      {fidx.loading ? <Loading /> : !(fidx.data ?? []).length ? (
        <Pending what="Proyecciones de demanda 2026-2030 con intervalos" expected={['data/forecasts/<run_id>/*.csv', 'artifacts/forecasting/*']} />
      ) : (fidx.data ?? []).slice(0, 4).map((f) => <ForecastFile key={f.source} file={f.file} source={f.source} />)}
    </Section>
  );
}

function ForecastFile({ file, source }: { file: string; source: string }) {
  const t = useJSON<Table>(file);
  const [varSel, setVarSel] = useState('');
  if (!t.data) return <Loading />;
  const cols = t.data.columns;
  const ci = (re: RegExp) => cols.findIndex((c) => re.test(c));
  const ip = ci(/^(period|periodo|trimestre|fecha|date)$/i), iv = ci(/^(value|valor|yhat|mean|pred|forecast|prediccion)$/i);
  const ilo = ci(/^(lower|lo|p5|p10|lo80|lower_80|yhat_lower|li)/i), ihi = ci(/^(upper|hi|p95|p90|hi80|upper_80|yhat_upper|ls)/i);
  const ivar = ci(/^(variable|target|serie)$/i), isc = ci(/^(scenario|scenario_id|escenario)$/i), iprov = ci(/^(prov_code|cod_prov)$/i);
  if (ip < 0 || iv < 0) return <Card title={source}><DataTable table={t.data} maxRows={20} /></Card>;
  let rows = t.data.rows;
  if (iprov >= 0) rows = rows.filter((r) => ['00', '0', 0, 'ES', null].includes(r[iprov] as never));
  const vars = ivar >= 0 ? [...new Set(rows.map((r) => String(r[ivar])))] : [''];
  const v = varSel || vars[0];
  if (ivar >= 0) rows = rows.filter((r) => String(r[ivar]) === v);
  const scen = isc >= 0 ? [...new Set(rows.map((r) => String(r[isc])))] : ['proyección'];
  const colors = ['var(--series-1)', 'var(--series-2)', 'var(--series-3)'];
  const series: Series[] = scen.slice(0, 3).map((s, i) => ({
    name: s, color: colors[i], dashed: true,
    points: rows.filter((r) => isc < 0 || String(r[isc]) === s).map((r) => ({ x: periodValue(String(r[ip])), y: r[iv] as number, lo: ilo >= 0 ? (r[ilo] as number) : null, hi: ihi >= 0 ? (r[ihi] as number) : null })).sort((a, b) => a.x - b.x),
  }));
  return (
    <Card title={`Proyección${v ? ` · ${humanize(v)}` : ''}`} subtitle={ilo >= 0 ? `Banda: ${cols[ilo]} – ${cols[ihi]}` : 'Sin intervalo publicado en el fichero'} source={<>Fuente: <code>{source}</code></>}>
      {vars.length > 1 && (
        <div className="controls"><Field id={`fv-${source}`} label="Variable"><select id={`fv-${source}`} className="select" value={v} onChange={(e) => setVarSel(e.target.value)}>{vars.map((x) => <option key={x}>{x}</option>)}</select></Field></div>
      )}
      <LineChart series={series} height={280} xFormat={(x) => String(Math.floor(x))} ariaLabel={`Proyección ${v}`} />
    </Card>
  );
}
