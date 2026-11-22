import { useApp } from '../App';
import { slotFile, slotIndex, useJSON } from '../lib/data';
import { fmtDate, fmtNum, fmtPeriod } from '../lib/format';
import { Card, Section, useReveal } from '../components/ui';

interface CatalogEntry { dataset: string; fuente: string; series_ids?: string[]; fecha_extraccion?: string }
interface PanelIndex { periods: string[]; provinces: Record<string, string>; variables: { key: string; scope?: string }[] }

export function Hero() {
  const { manifest } = useApp();
  const cat = useJSON<CatalogEntry[]>(slotFile(manifest, 'sources'));
  const panel = useJSON<PanelIndex>(slotFile(manifest, 'panel_trimestral'));
  const ref = useReveal<HTMLDivElement>();
  const list = Array.isArray(cat.data) ? cat.data.filter((d) => !/tinsa/i.test(d.fuente)) : [];
  const nSeries = list.reduce((a, d) => a + (d.series_ids?.length ?? 0), 0);
  const orgs = [...new Set(list.map((d) => d.fuente.toUpperCase()))];
  const p = panel.data;
  const facts = [
    { v: list.length ? fmtNum(list.length, 0) : '—', l: 'conjuntos de datos en el catálogo', s: orgs.length ? orgs.join(' · ') : 'catálogo pendiente' },
    { v: nSeries ? fmtNum(nSeries, 0) : '—', l: 'identificadores de serie descargados', s: 'vía API oficial, con snapshot y hash' },
    { v: p ? fmtNum(Object.keys(p.provinces).length, 0) : '—', l: 'provincias (código INE)', s: 'panel trimestral v2' },
    { v: p ? `${fmtPeriod(p.periods[0])} – ${fmtPeriod(p.periods[p.periods.length - 1])}` : '—', l: 'cobertura temporal del panel', s: p ? `${p.periods.length} trimestres` : 'panel pendiente' },
  ];
  return (
    <section id="portada" className="hero" aria-labelledby="portada-t">
      <div className="hero__grid" aria-hidden="true" />
      <div ref={ref} className="reveal">
        <span className="hero__eyebrow"><span className="status-dot" style={{ background: 'var(--brand-accent)' }} />Trabajo Fin de Máster · Business Analytics, IA y ML</span>
        <h1 id="portada-t" className="hero__title">Analítica avanzada del <em>mercado hipotecario</em> español</h1>
        <p className="hero__lead">
          Plataforma de un equipo de Data Science para entender, explicar y proyectar la demanda hipotecaria por provincia:
          datos oficiales trazables, econometría de series temporales, modelos de predicción validados frente a referencias
          ingenuas y un simulador de esfuerzo transparente.
        </p>
        <div className="row hero__cta">
          <a className="btn btn--primary" href="#panel">Explorar el panel provincial</a>
          <a className="btn btn--secondary" href="#simulador">Probar el simulador</a>
          <a className="btn btn--ghost" href="#estado">Estado de los datos →</a>
        </div>
        <div className="hero__facts">
          {facts.map((f) => (
            <div key={f.l} className="card kpi card--flat">
              <span className="kpi__value kpi__value--sm num">{f.v}</span>
              <span className="kpi__label">{f.l}</span>
              <span className="kpi__period">{f.s}</span>
            </div>
          ))}
        </div>
        <p className="xs muted mt-4">Cifras calculadas en el navegador a partir de <code>data/metadata/series_catalog.yaml</code> y <code>data/processed/panel_trimestral.csv</code>{manifest?.slots.sources?.updated && <> · catálogo actualizado {fmtDate(manifest.slots.sources.updated, true)}</>}.</p>
      </div>
    </section>
  );
}

const Icon = ({ d }: { d: string }) => <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true"><path d={d} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>;

export function Problem() {
  const items = [
    { i: 'M3 17l6-6 4 4 8-8M14 7h7v7', t: 'Anticipar la demanda', d: 'Planificar capacidad comercial, capital y campañas exige saber cuántas hipotecas se constituirán por provincia en los próximos trimestres, y con qué incertidumbre.' },
    { i: 'M12 3v18M5 8h14M7 8l-3 7h6zM17 8l-3 7h6z', t: 'Entender los determinantes', d: 'Separar el papel del Euríbor, la renta, el precio de la vivienda y los costes de construcción mediante econometría con supuestos explícitos (asociación, no causalidad).' },
    { i: 'M4 6h16M4 12h10M4 18h7', t: 'Datos trazables y actualizables', d: 'Sustituir hojas de cálculo manuales por un pipeline reproducible: descargas por API, snapshots con hash, controles de calidad y fecha de referencia separada de la de publicación.' },
    { i: 'M12 2l8 4v6c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V6z', t: 'Transparencia ante el cliente', d: 'Un simulador que explica la cuota, los gastos y el esfuerzo con fórmulas deterministas y supuestos visibles, sin emitir decisiones de concesión.' },
  ];
  return (
    <Section id="problema" num={2} kicker="Contexto" title="Problema de negocio"
      lead="La hipoteca es el producto de mayor plazo e importe de la banca minorista. Las decisiones sobre él combinan ciclo macroeconómico, heterogeneidad territorial y exigencias de explicabilidad.">
      <div className="feature-grid">
        {items.map((x) => (
          <div key={x.t} className="card feature">
            <div className="feature__icon"><Icon d={x.i} /></div>
            <h3>{x.t}</h3>
            <p>{x.d}</p>
          </div>
        ))}
      </div>
      <div className="callout">
        <strong>Alcance.</strong> Atalaya es una herramienta analítica y académica. No es un motor de admisión de riesgos: no evalúa solvencia,
        no aprueba ni deniega operaciones y no sustituye la información precontractual (FEIN) de una entidad.
      </div>
    </Section>
  );
}

const STEPS = [
  { t: 'Fuentes', c: 'INE · BCE · Eurostat · MIVAU', p: 'APIs oficiales (Tempus3, Data Portal, SDMX) y ficheros públicos registrados con URL y fecha.' },
  { t: 'Raw', c: 'data/raw/<fuente>/<fecha>', p: 'Snapshot original + meta.json: URL, parámetros, fecha de extracción, sha256, licencia.' },
  { t: 'Staging', c: 'data/staging/', p: 'Formato largo normalizado: prov_code INE, periodo, unidad, estado provisional/definitivo.' },
  { t: 'Processed', c: 'data/processed/', p: 'Panel trimestral provincial y nacional, panel anual sin replicar. Validación y reconciliación.' },
  { t: 'Modelos', c: 'src/models/', p: 'Raíces unitarias, cointegración, VECM/VAR, panel; predicción con validación rolling-origin.' },
  { t: 'Artefactos', c: 'artifacts/<dominio>/', p: 'JSON/CSV versionados: econometría, forecasting, demanda, simulador, calidad de datos.' },
  { t: 'App y web', c: 'Web/ · site/', p: 'La aplicación bancaria y esta web leen solo artefactos: ninguna cifra se escribe a mano.', out: true },
];

export function Architecture() {
  const { manifest } = useApp();
  const ok = (k: string) => manifest?.slots[k]?.status === 'ok';
  const runs = useJSON<{ updated: string }[]>(slotIndex(manifest, 'pipeline_runs'));
  return (
    <Section id="arquitectura" num={3} kicker="Ingeniería de datos" title="Arquitectura de datos"
      lead="Cada cifra que aparece en esta web recorre el mismo camino, de la fuente oficial al artefacto publicado, y puede rastrearse hasta su snapshot original.">
      <div className="pipeline" role="list" aria-label="Etapas del pipeline">
        {STEPS.map((s) => (
          <div key={s.t} className={`pipe-step${s.out ? ' pipe-step--out' : ''}`} role="listitem">
            <h4>{s.t}</h4>
            <code>{s.c}</code>
            <p>{s.p}</p>
          </div>
        ))}
      </div>
      <div className="grid-2 grid-2--even">
        <Card title="Contratos entre capas" className="card--flat">
          <ul className="small">
            <li>Identificador de provincia canónico: código INE de 2 dígitos (<code>prov_code</code> 01–52), sin emparejar por nombres.</li>
            <li>Periodo canónico <code>YYYYQn</code>; la fecha de referencia se distingue de la de publicación.</li>
            <li>Variables anuales sin replicar en trimestres; variables nacionales marcadas como tales.</li>
            <li>Proyecciones separadas (<code>data/forecasts/</code>) con <code>is_projection</code>, modelo, fin de entrenamiento y escenario.</li>
          </ul>
        </Card>
        <Card title="Estado de las capas en esta compilación" className="card--flat">
          <ul className="small" style={{ listStyle: 'none', padding: 0 }}>
            {[
              ['Catálogo de fuentes', 'sources'], ['Procedencia de snapshots', 'provenance'], ['Panel trimestral', 'panel_trimestral'],
              ['Serie nacional', 'nacional_trimestral'], ['Controles de calidad', 'artifacts:data_quality'], ['Econometría', 'artifacts:econometrics'],
              ['Forecasting', 'artifacts:forecasting'], ['Proyecciones', 'forecasts'],
            ].map(([l, k]) => (
              <li key={k} className="row" style={{ justifyContent: 'space-between' }}>
                <span>{l}</span>
                {ok(k) ? <span className="badge badge--good">✓ disponible</span> : <span className="badge badge--neutral">◌ pendiente</span>}
              </li>
            ))}
          </ul>
          {runs.data && runs.data.length > 0 && <p className="xs muted mt-2">Última ejecución registrada: {fmtDate(runs.data[0].updated, true)}</p>}
        </Card>
      </div>
    </Section>
  );
}
