import { useEffect, useMemo, useState } from 'react';
import { useApp } from '../App';
import { slotFile, slotIndex, useJSON, type ArtifactItem, type Table } from '../lib/data';
import { varLabel } from '../lib/dict';
import { fmtDate, fmtNum, fmtPeriod, periodValue } from '../lib/format';
import { Card, DataTable, ErrorBox, Field, JsonView, Loading, Pending, Section, SourceLine } from '../components/ui';
import { ChoroplethMap, type GeoFC } from '../components/ChoroplethMap';
import { LineChart, BarChart, type Series } from '../components/charts';

const ORG: Record<string, string> = { ine: 'INE', ecb: 'BCE', bce: 'BCE', eurostat: 'Eurostat', mivau: 'MIVAU', bde: 'Banco de España', tinsa: 'Tinsa' };
const FREQ: Record<string, string> = { M: 'Mensual', Q: 'Trimestral', A: 'Anual', S: 'Semestral', D: 'Diaria' };
const GEO: Record<string, string> = { provincia: 'Provincial', ccaa: 'Autonómico', nacional: 'Nacional', zona_euro: 'Zona euro' };

interface CatalogEntry {
  dataset: string; fuente: string; tabla_o_clave?: string; frecuencia?: string; series_ids?: string[]; url_documentacion?: string;
  ultima_modificacion_origen?: string; fecha_extraccion?: string; retraso_publicacion?: string; metodologia?: string;
  variables?: { nombre: string; unidad?: string }[]; opcional?: boolean;
}

export function Sources() {
  const { manifest, dict } = useApp();
  const cat = useJSON<CatalogEntry[] | { fuentes?: CatalogEntry[] }>(slotFile(manifest, 'sources'));
  const list: CatalogEntry[] = Array.isArray(cat.data) ? cat.data : (cat.data?.fuentes ?? []);
  const ambito = (d: CatalogEntry) => {
    const g = new Set((d.variables ?? []).map((v) => dict[v.nombre]?.geo).filter(Boolean) as string[]);
    if (!g.size) Object.values(dict).forEach((v) => v.dataset === d.dataset && v.geo && g.add(v.geo));
    return [...g].map((x) => GEO[x] ?? x).join(' · ') || '—';
  };
  return (
    <Section id="fuentes" num={4} kicker="Datos" title="Fuentes y metodología"
      lead="Todas las series se descargan de organismos oficiales mediante su API o ficheros públicos, se guardan como snapshot con hash y se documentan en un catálogo versionado.">
      {cat.loading ? <Loading /> : !list.length ? (
        <Pending what="Catálogo de fuentes" expected={['data/metadata/series_catalog.yaml']} />
      ) : (
        <Card title="Catálogo de series" subtitle="Leído de data/metadata/series_catalog.yaml; el ámbito se deriva del diccionario de variables."
          source={<SourceLine manifest={manifest} slots={['sources', 'variables']} />}>
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Catálogo de fuentes">
            <table className="table table--compact">
              <thead><tr><th>Organismo</th><th>Conjunto</th><th>Tabla / id de serie</th><th className="num">Series</th><th>Frecuencia</th><th>Ámbito</th><th>Última modificación en origen</th><th>Extracción</th></tr></thead>
              <tbody>
                {list.map((d) => {
                  const excluded = /tinsa/i.test(d.fuente);
                  return (
                    <tr key={d.dataset}>
                      <td><strong>{ORG[d.fuente?.toLowerCase()] ?? d.fuente}</strong></td>
                      <td>{d.url_documentacion ? <a href={d.url_documentacion} target="_blank" rel="noopener noreferrer">{d.dataset}</a> : d.dataset}
                        {excluded && <div><span className="badge badge--warn">⚠ no publicada en la web</span></div>}
                        {d.metodologia && <div className="xs muted">{d.metodologia.slice(0, 120)}{d.metodologia.length > 120 ? '…' : ''}</div>}</td>
                      <td><code>{d.tabla_o_clave ?? '—'}</code>{d.series_ids && d.series_ids.length <= 3 && <div className="xs muted">{d.series_ids.join(', ')}</div>}</td>
                      <td className="num">{fmtNum(d.series_ids?.length ?? null, 0)}</td>
                      <td>{FREQ[d.frecuencia ?? ''] ?? d.frecuencia ?? '—'}</td>
                      <td>{ambito(d)}</td>
                      <td className="xs">{d.ultima_modificacion_origen ?? '—'}{d.retraso_publicacion && <div className="muted">Publicación: {d.retraso_publicacion}</div>}</td>
                      <td className="xs nowrap">{/^\d{4}-/.test(d.fecha_extraccion ?? '') ? fmtDate(d.fecha_extraccion, true) : d.fecha_extraccion ?? '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="xs muted mt-2">Las series de Tinsa se usaron en la versión 1 del proyecto; sus condiciones de uso no permiten explotar su contenido sin autorización, por lo que esta web no las publica. El precio por m² que se muestra es el valor tasado de vivienda libre del MIVAU.</p>
        </Card>
      )}
      <div className="grid-2 grid-2--even">
        <Card title="Principios metodológicos" className="card--flat">
          <ul className="small">
            <li><strong>Fecha de referencia ≠ fecha de publicación.</strong> Los datos se fechan por su periodo de referencia; el retraso de publicación se documenta por fuente.</li>
            <li><strong>Sin interpolación por comodidad.</strong> Las variables anuales no se reparten en trimestres; viven en el panel anual.</li>
            <li><strong>Agregación declarada.</strong> Cada variable indica cómo se pasa de mensual a trimestral (suma, media o sin agregación).</li>
            <li><strong>Sin datos futuros en el pasado.</strong> Las validaciones de predicción usan solo información disponible en cada origen.</li>
          </ul>
        </Card>
        <Card title="Diccionario de variables" subtitle="Variables del panel trimestral con unidad y fuente" className="card--flat">
          {Object.keys(dict).length ? (
            <DataTable maxRows={8} table={{
              columns: ['Variable', 'Unidad', 'Ámbito', 'Fuente'],
              rows: Object.values(dict).filter((v) => v.unit && !/tinsa/i.test(v.key)).map((v) => [v.label, v.unit ?? '', GEO[v.geo ?? ''] ?? v.geo ?? '', ORG[v.source ?? ''] ?? v.source ?? '']),
            }} />
          ) : <Pending what="Diccionario" expected={['data/metadata/data_dictionary.csv']} />}
        </Card>
      </div>
    </Section>
  );
}

interface PanelIndex { periods: string[]; provinces: Record<string, string>; variables: { key: string; file: string; scope?: string; n_values: number }[] }

export function ProvincialPanel() {
  const { manifest, dict } = useApp();
  const idx = useJSON<PanelIndex>(slotFile(manifest, 'panel_trimestral'));
  const geo = useJSON<GeoFC>(slotFile(manifest, 'geo'));
  const vars = useMemo(() => (idx.data?.variables ?? []).filter((v) => v.scope !== 'nacional'), [idx.data]);
  const [varKey, setVarKey] = useState<string>('');
  useEffect(() => {
    if (!vars.length || varKey) return;
    setVarKey((vars.find((v) => v.key === 'precio_m2_mivau_tasado') ?? vars.find((v) => v.key === 'hipotecas_viviendas_num') ?? vars[0]).key);
  }, [vars, varKey]);
  const vinfo = vars.find((v) => v.key === varKey);
  const vals = useJSON<Record<string, Record<string, number>>>(vinfo?.file);
  const periods = useMemo(() => Object.keys(vals.data ?? {}).sort((a, b) => periodValue(a) - periodValue(b)), [vals.data]);
  const [period, setPeriod] = useState('');
  useEffect(() => { if (periods.length && !periods.includes(period)) setPeriod(periods[periods.length - 1]); }, [periods, period]);
  const values = vals.data?.[period] ?? {};
  const names = idx.data?.provinces ?? {};
  const unit = dict[varKey]?.unit;
  const fmt = (v: number) => fmtNum(v, Math.abs(v) >= 100 ? 0 : 1);
  const ranking = Object.entries(values).filter(([, v]) => Number.isFinite(v)).sort((a, b) => b[1] - a[1]);
  const [showTable, setShowTable] = useState(false);

  return (
    <Section id="panel" num={5} kicker="Exploración" title="Panel provincial"
      lead="Mapa coroplético por provincia (quintiles) para cualquier variable provincial o autonómica del panel trimestral v2. Las variables nacionales replicadas no se cartografían.">
      {idx.loading || geo.loading ? <Loading /> : idx.error || !idx.data ? (
        <Pending what="Panel trimestral" expected={['data/processed/panel_trimestral.csv']} note={manifest?.slots.panel_trimestral?.note} />
      ) : !geo.data ? <Pending what="Geometría provincial" expected={['Web/static/spain-provinces.geojson']} /> : (
        <>
          <div className="controls">
            <Field id="panel-var" label="Variable">
              <select id="panel-var" className="select" value={varKey} onChange={(e) => setVarKey(e.target.value)}>
                {vars.map((v) => <option key={v.key} value={v.key}>{varLabel(dict, v.key)}{dict[v.key]?.unit ? ` (${dict[v.key].unit})` : ''}</option>)}
              </select>
            </Field>
            <Field id="panel-period" label="Trimestre">
              <select id="panel-period" className="select" value={period} onChange={(e) => setPeriod(e.target.value)}>
                {[...periods].reverse().map((p) => <option key={p} value={p}>{fmtPeriod(p)}</option>)}
              </select>
            </Field>
            <button className="btn btn--secondary" onClick={() => setShowTable(!showTable)} aria-expanded={showTable}>{showTable ? 'Ver mapa' : 'Ver tabla'}</button>
          </div>
          <div className="grid-2">
            <Card title={`${varLabel(dict, varKey)} · ${fmtPeriod(period)}`} subtitle={unit ? `Unidad: ${unit}${dict[varKey]?.geo === 'ccaa' ? ' · dato autonómico asignado a sus provincias' : ''}` : undefined}
              source={<SourceLine manifest={manifest} slots={['panel_trimestral', 'geo']} extra={dict[varKey]?.dataset && <>serie: <code>{dict[varKey].dataset}</code></>} />}>
              {vals.loading ? <Loading /> : vals.error ? <ErrorBox msg={vals.error} /> : showTable ? (
                <DataTable maxRows={60} table={{ columns: ['Código', 'Provincia', `Valor${unit ? ` (${unit})` : ''}`], rows: ranking.map(([c, v]) => [c, names[c] ?? c, v]) }} />
              ) : (
                <ChoroplethMap geo={geo.data} values={values} label={`${varLabel(dict, varKey)}, ${fmtPeriod(period)}`} format={fmt} names={names} />
              )}
            </Card>
            <Card title="Ranking provincial" subtitle={`${ranking.length} provincias con dato`}>
              {ranking.length ? (
                <>
                  <p className="kpi__label">Diez valores más altos</p>
                  <BarChart ariaLabel="Diez provincias con valor más alto" rows={ranking.slice(0, 10).map(([c, v]) => ({ label: names[c] ?? c, value: v }))} format={fmt} />
                  <p className="kpi__label mt-4">Cinco valores más bajos</p>
                  <BarChart ariaLabel="Cinco provincias con valor más bajo" color="var(--seq-300)" rows={ranking.slice(-5).reverse().map(([c, v]) => ({ label: names[c] ?? c, value: v }))} format={fmt} />
                </>
              ) : <p className="muted small">Sin datos para este trimestre.</p>}
            </Card>
          </div>
        </>
      )}
    </Section>
  );
}

function nationalSeries(t: Table | undefined, col: string, color: string, name: string): Series | null {
  if (!t) return null;
  const i = t.columns.indexOf(col), ip = t.columns.indexOf('period');
  if (i < 0 || ip < 0) return null;
  const points = t.rows.map((r) => ({ x: periodValue(String(r[ip])), y: typeof r[i] === 'number' ? (r[i] as number) : null })).filter((p) => Number.isFinite(p.x));
  return points.some((p) => p.y != null) ? { name, color, points } : null;
}
const qFmt = (x: number) => String(Math.floor(x + 1e-9));

export function Economic() {
  const { manifest, dict } = useApp();
  const nat = useJSON<Table>(slotFile(manifest, 'nacional_trimestral'));
  const econ = useJSON<ArtifactItem[]>(slotIndex(manifest, 'artifacts:economics'));
  const t = nat.data;
  const charts: { title: string; sub: string; series: (Series | null)[]; fmt?: (v: number) => string; unit?: string }[] = [
    { title: 'Hipotecas sobre viviendas', sub: 'Número de hipotecas constituidas por trimestre, España (INE)', series: [nationalSeries(t, 'hipotecas_viviendas_num', 'var(--series-1)', 'Hipotecas sobre viviendas')], fmt: (v) => fmtNum(v, 0) },
    { title: 'Coste de financiación', sub: 'Euríbor 12M y TAE de nuevas hipotecas, % (BCE)', series: [nationalSeries(t, 'euribor_12m', 'var(--series-1)', 'Euríbor 12M'), nationalSeries(t, 'tae_vivienda', 'var(--series-2)', 'TAE nuevas operaciones vivienda')], fmt: (v) => fmtNum(v, 1) + ' %' },
    { title: 'Compraventas de viviendas', sub: 'Número por trimestre, España (INE, ETDP)', series: [nationalSeries(t, 'compraventas_viviendas_num', 'var(--series-3)', 'Compraventas')], fmt: (v) => fmtNum(v, 0) },
    { title: 'Mercado laboral', sub: 'Tasa de paro, % de la población activa (INE, EPA)', series: [nationalSeries(t, 'tasa_paro', 'var(--series-7)', 'Tasa de paro')], fmt: (v) => fmtNum(v, 1) + ' %' },
  ];
  const econFiles = (econ.data ?? []).filter((i) => i.file && i.kind === 'json');
  return (
    <Section id="economia" num={6} kicker="Contexto macroeconómico" title="Análisis económico"
      lead="Evolución nacional de la demanda hipotecaria y de sus condicionantes. Series trimestrales oficiales; agregación nacional declarada en el diccionario de variables.">
      {nat.loading ? <Loading /> : !t ? <Pending what="Serie nacional" expected={['data/processed/nacional_trimestral.csv']} /> : (
        <div className="grid-2 grid-2--even">
          {charts.map((c) => {
            const s = c.series.filter(Boolean) as Series[];
            return (
              <Card key={c.title} title={c.title} subtitle={c.sub} source={<SourceLine manifest={manifest} slots={['nacional_trimestral']} />}>
                {s.length ? <LineChart series={s} height={240} xFormat={qFmt} yFormat={c.fmt} ariaLabel={`${c.title}: ${c.sub}`} /> : <p className="muted small">Variable no disponible en el panel.</p>}
              </Card>
            );
          })}
        </div>
      )}
      {econFiles.length > 0 && econFiles.map((f) => <EconArtifact key={f.name} item={f} />)}
      <p className="xs muted">Variables: {['hipotecas_viviendas_num', 'euribor_12m', 'tae_vivienda', 'compraventas_viviendas_num', 'tasa_paro'].map((k) => `${varLabel(dict, k)}${dict[k]?.unit ? ` (${dict[k].unit})` : ''}`).join(' · ')}.</p>
    </Section>
  );
}
function EconArtifact({ item }: { item: ArtifactItem }) {
  const d = useJSON(item.file);
  return <Card title={item.name} source={<>Fuente: <code>{item.source}</code></>}>{d.data ? <JsonView data={d.data} /> : <Loading />}</Card>;
}
