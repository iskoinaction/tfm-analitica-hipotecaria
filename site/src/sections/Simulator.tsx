import { useEffect, useMemo, useState } from 'react';
import { useApp } from '../App';
import { artifactFile, slotFile, slotIndex, useJSON, type ArtifactItem, type Table } from '../lib/data';
import { fmtEUR, fmtNum, fmtPeriod } from '../lib/format';
import { AVISOS_LEGALES, politicaDe, simular, type Aranceles, type Entrada, type Modalidad, type Regla, type Resultado } from '../lib/advisor';
import { Card, Field, Loading, Pending, Section } from '../components/ui';

interface PanelIndex { provinces: Record<string, string>; ccaa?: Record<string, string> }
const pct = (v: number | null | undefined, d = 1) => (v == null || !Number.isFinite(v) ? '—' : `${fmtNum(v * 100, d)} %`);
const BADGE = { verde: ['badge badge--good', '● Esfuerzo dentro de la referencia'], ambar: ['badge badge--warn', '▲ Esfuerzo por encima de la referencia'], rojo: ['badge badge--crit', '■ Esfuerzo elevado'] } as const;

function NumField({ id, label, value, onChange, unit, hint, min = 0, step = 1 }: { id: string; label: string; value: number; onChange: (v: number) => void; unit?: string; hint?: string; min?: number; step?: number }) {
  const bad = !Number.isFinite(value) || value < min;
  return (
    <Field id={id} label={label} hint={hint} error={bad ? `Introduzca un valor numérico ≥ ${min}` : undefined}>
      <div className="input-group">
        <input id={id} className="input" type="number" inputMode="decimal" min={min} step={step} value={Number.isFinite(value) ? value : ''}
          aria-invalid={bad} aria-describedby={hint ? `${id}-hint` : undefined} onChange={(e) => onChange(e.target.value === '' ? NaN : Number(e.target.value))} />
        {unit && <span className="input-group__addon">{unit}</span>}
      </div>
    </Field>
  );
}

export function Simulator() {
  const { manifest } = useApp();
  const idx = useJSON<ArtifactItem[]>(slotIndex(manifest, 'artifacts:advisor'));
  const fiscalItem = artifactFile(idx.data, /^fiscal_tables\.json$/);
  const fiscal = useJSON<{ reglas: Regla[]; aranceles: Aranceles }>(fiscalItem?.file);
  const policy = useJSON<Record<string, unknown>>(slotFile(manifest, 'advisor_policy'));
  const panel = useJSON<PanelIndex>(slotFile(manifest, 'panel_trimestral'));
  const nat = useJSON<Table>(slotFile(manifest, 'nacional_trimestral'));
  const mivau = useJSON<Record<string, Record<string, number>>>('data/panel/panel_trimestral/precio_m2_mivau_tasado.json');
  const pol = useMemo(() => politicaDe(policy.data as never), [policy.data]);

  // Tipo de mercado de referencia: TEDR medio de nuevas operaciones de vivienda, último trimestre publicado (BCE)
  const ref = useMemo(() => {
    const t = nat.data; if (!t) return null;
    const i = t.columns.indexOf('tedr_vivienda'), ip = t.columns.indexOf('period');
    for (let k = t.rows.length - 1; k >= 0; k--) if (typeof t.rows[k][i] === 'number') return { v: t.rows[k][i] as number, p: String(t.rows[k][ip]) };
    return null;
  }, [nat.data]);

  const [f, setF] = useState({ prov: '28', tipo: 'usada' as 'usada' | 'nueva', habitual: true, precio: 250000, aportacion: 60000, ingresos: 3000, deudas: 0, edad: 35, plazo: 25, mod: 'fijo' as Modalidad, tin: NaN, tinVar: NaN, anios: 5 });
  useEffect(() => { if (ref && Number.isNaN(f.tin)) setF((s) => ({ ...s, tin: Number(ref.v.toFixed(2)), tinVar: Number((ref.v + 0.5).toFixed(2)) })); }, [ref, f.tin]);
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((s) => ({ ...s, [k]: v }));

  const ccaa = panel.data?.ccaa?.[f.prov];
  const hoy = new Date().toISOString().slice(0, 10);
  const valid = [f.precio, f.aportacion, f.ingresos, f.edad, f.plazo, f.tin].every((x) => Number.isFinite(x)) && f.precio >= 1000 && f.ingresos >= 0 && f.edad >= 18 && f.plazo >= 1;
  const res: Resultado | { error: string } | null = useMemo(() => {
    if (!fiscal.data || !ccaa || !valid) return null;
    const e: Entrada = { ccaa, precio: f.precio, tipoVivienda: f.tipo, viviendaHabitual: f.habitual, aportacion: f.aportacion, ingresosNetosMes: f.ingresos, otrasDeudasMes: f.deudas || 0,
      edad: f.edad, plazoAnios: f.plazo, modalidad: f.mod, tinPct: f.tin, tinVariablePct: Number.isFinite(f.tinVar) ? f.tinVar : null, aniosFijos: f.anios, fecha: hoy };
    try { return simular(e, fiscal.data.reglas, fiscal.data.aranceles, pol); } catch (err) { return { error: (err as Error).message }; }
  }, [fiscal.data, ccaa, valid, f, pol, hoy]);

  const prices = mivau.data ? Object.entries(mivau.data).sort(([a], [b]) => a.localeCompare(b)).at(-1) : undefined;
  const mivauM2 = prices?.[1]?.[f.prov];

  return (
    <Section id="simulador" num={10} kicker="Asesor interactivo" title="Simulador hipotecario"
      lead="Calcula cuota, gastos de compra y esfuerzo con fórmulas deterministas y supuestos visibles. Todo se calcula en su navegador: ningún dato se envía a ningún servidor.">
      <div className="callout callout--warn" role="note"><strong>No es asesoramiento ni scoring.</strong> El indicador de esfuerzo usa umbrales ilustrativos; no evalúa solvencia ni concede o deniega nada.</div>
      {fiscal.loading || idx.loading ? <Loading /> : !fiscalItem || !fiscal.data ? (
        <Pending what="Tablas fiscales del simulador" expected={['artifacts/advisor/fiscal_tables.json']} />
      ) : (
        <div className="sim">
          <Card title="Su operación" subtitle="Valores de ejemplo editables">
            <form className="stack" onSubmit={(e) => e.preventDefault()} aria-label="Datos de la operación">
              <fieldset><legend>Vivienda</legend>
                <div className="form-grid">
                  <Field id="s-prov" label="Provincia"><select id="s-prov" className="select" value={f.prov} onChange={(e) => set('prov', e.target.value)}>
                    {Object.entries(panel.data?.provinces ?? {}).sort((a, b) => a[1].localeCompare(b[1], 'es')).map(([c, n]) => <option key={c} value={c}>{n}</option>)}</select></Field>
                  <Field id="s-tipo" label="Tipo de vivienda"><select id="s-tipo" className="select" value={f.tipo} onChange={(e) => set('tipo', e.target.value as 'usada' | 'nueva')}><option value="usada">Usada (ITP)</option><option value="nueva">Nueva (IVA/IGIC + AJD)</option></select></Field>
                  <NumField id="s-precio" label="Precio de la vivienda" unit="€" value={f.precio} onChange={(v) => set('precio', v)} min={1000} step={1000}
                    hint={mivauM2 != null ? `Referencia MIVAU (valor tasado) en la provincia: ${fmtNum(mivauM2, 0)} €/m² (${fmtPeriod(prices![0])})` : undefined} />
                  <Field id="s-hab" label="Vivienda habitual"><select id="s-hab" className="select" value={f.habitual ? 's' : 'n'} onChange={(e) => set('habitual', e.target.value === 's')}><option value="s">Sí</option><option value="n">No</option></select></Field>
                </div>
              </fieldset>
              <fieldset><legend>Perfil económico</legend>
                <div className="form-grid">
                  <NumField id="s-aport" label="Aportación propia (ahorro)" unit="€" value={f.aportacion} onChange={(v) => set('aportacion', v)} step={1000} hint="Cubre entrada y gastos; el resto se financia." />
                  <NumField id="s-ing" label="Ingresos netos mensuales" unit="€" value={f.ingresos} onChange={(v) => set('ingresos', v)} step={50} />
                  <NumField id="s-deu" label="Otras cuotas de deuda al mes" unit="€" value={f.deudas} onChange={(v) => set('deudas', v)} step={25} />
                  <NumField id="s-edad" label="Edad del titular de mayor edad" unit="años" value={f.edad} onChange={(v) => set('edad', v)} min={18} />
                </div>
              </fieldset>
              <fieldset><legend>Préstamo</legend>
                <div className="form-grid">
                  <NumField id="s-plazo" label="Plazo" unit="años" value={f.plazo} onChange={(v) => set('plazo', v)} min={1} />
                  <Field id="s-mod" label="Modalidad"><select id="s-mod" className="select" value={f.mod} onChange={(e) => set('mod', e.target.value as Modalidad)}><option value="fijo">Fijo</option><option value="variable">Variable</option><option value="mixto">Mixto</option></select></Field>
                  <NumField id="s-tin" label={f.mod === 'mixto' ? 'TIN del tramo fijo' : 'TIN inicial'} unit="%" value={f.tin} onChange={(v) => set('tin', v)} min={-1} step={0.05}
                    hint={ref ? `Por defecto: TEDR medio BCE de nuevas operaciones de vivienda, ${fmtPeriod(ref.p)} (${fmtNum(ref.v, 2)} %). No es una oferta.` : 'Introduzca el tipo de su oferta.'} />
                  {f.mod === 'mixto' && (<>
                    <NumField id="s-tinv" label="TIN del tramo variable" unit="%" value={f.tinVar} onChange={(v) => set('tinVar', v)} min={-1} step={0.05} />
                    <NumField id="s-anios" label="Años a tipo fijo" unit="años" value={f.anios} onChange={(v) => set('anios', v)} min={1} />
                  </>)}
                </div>
              </fieldset>
            </form>
          </Card>
          <div className="sim__results" aria-live="polite">
            {!res ? <Card><p className="muted">{!valid ? 'Complete los campos con valores válidos para ver el resultado.' : 'Calculando…'}</p></Card>
              : 'error' in res ? <div className="callout callout--crit" role="alert">{res.error}</div> : <Results r={res} f={f} pol={pol} />}
          </div>
        </div>
      )}
      <details className="card card--flat"><summary className="small"><strong>Metodología, validación y avisos legales</strong></summary>
        <ul className="small mt-2">
          <li>Cuota francesa C = P·r / (1 − (1+r)<sup>−n</sup>), r = TIN/12; capital financiado = precio + gastos de compra − aportación.</li>
          <li>Gastos: impuesto (ITP, o IVA/IGIC + AJD en vivienda nueva) de <code>artifacts/advisor/fiscal_tables.json</code> con vigencias y fuente; aranceles notariales y registrales base (RD 1426 y 1427/1989).</li>
          <li>DSTI = (cuota + otras deudas) / ingresos netos; con tipo variable o mixto se calcula también con +{fmtNum(pol.estresPp, 0)} pp. LTV sobre min(precio, tasación).</li>
          <li>Esta implementación JavaScript se verifica con una prueba automática (vitest) contra los 18 casos de <code>artifacts/advisor/test_vectors.json</code> generados por el motor Python del repositorio.</li>
        </ul>
        <ul className="small">{AVISOS_LEGALES.map((a) => <li key={a}>{a}</li>)}</ul>
      </details>
    </Section>
  );
}

function Results({ r, f, pol }: { r: Resultado; f: { mod: Modalidad; tin: number }; pol: ReturnType<typeof politicaDe> }) {
  const [cls, label] = BADGE[r.semaforo];
  const d = r.estresAplicado ? r.dstiEstres : r.dsti;
  const max = 0.6;
  return (
    <div className="stack">
      <Card className="card--accent" title="Resultado orientativo" actions={<span className={cls}>{label}</span>}>
        <div className="result-grid">
          <div className="kpi"><span className="kpi__label">Cuota mensual inicial</span><span className="kpi__value num">{fmtEUR(r.cuota, 0)}</span><span className="kpi__period">TIN {fmtNum(f.tin, 2)} % · {r.plazoAnios} años</span></div>
          <div className="kpi"><span className="kpi__label">Capital a financiar</span><span className="kpi__value num">{fmtEUR(r.capital, 0)}</span><span className="kpi__period">LTV {pct(r.ltv)} · LTI {fmtNum(r.lti, 1)}×</span></div>
        </div>
        <div className="mt-4">
          <p className="kpi__label">Esfuerzo (DSTI){r.estresAplicado ? ` con estrés +${fmtNum(pol.estresPp, 0)} pp` : ''}: <strong className="num">{pct(d)}</strong></p>
          <div className="meter" role="img" aria-label={`DSTI ${pct(d)}; referencia ${pct(pol.dstiRef, 0)}`}>
            <div className="meter__bar" style={{ width: `${Math.min(100, ((d ?? 0) / max) * 100)}%`, background: r.semaforo === 'verde' ? 'var(--status-good)' : r.semaforo === 'ambar' ? 'var(--status-warn)' : 'var(--status-crit)' }} />
            <span className="meter__mark" style={{ left: `${(pol.dstiRef / max) * 100}%` }} title="Referencia" />
          </div>
          <p className="xs muted mt-2">{r.motivo} Indicador de capacidad de pago con umbrales ilustrativos; no es una decisión de concesión.</p>
        </div>
        <dl className="dl mt-4">
          <dt>Cuota con +{fmtNum(pol.estresPp, 0)} pp{r.estresAplicado ? '' : ' (no aplica a tipo fijo)'}</dt><dd>{fmtEUR(r.cuotaEstres, 0)}</dd>
          {r.cuotaTrasFijo != null && (<><dt>Cuota tras el periodo fijo</dt><dd>{fmtEUR(r.cuotaTrasFijo, 0)}</dd></>)}
          <dt>Intereses totales</dt><dd>{fmtEUR(r.totalIntereses, 0)}</dd>
          <dt>Total pagado (capital + intereses)</dt><dd>{fmtEUR(r.totalPagado, 0)}</dd>
          <dt>Entrada necesaria para LTV {Math.round(pol.ltvRef * 100)} %</dt><dd>{fmtEUR(r.entradaNecesariaLtv, 0)}</dd>
          <dt>Capital máximo con DSTI ≤ {Math.round(pol.dstiRef * 100)} %</dt><dd>{fmtEUR(r.capitalMaxDsti, 0)}</dd>
        </dl>
      </Card>
      <Card title="Gastos de compra a cargo del cliente" subtitle="La notaría, registro, gestoría y AJD del préstamo corresponden a la entidad (Ley 5/2019, art. 14.1.e)">
        <dl className="dl">
          {r.gastos.lineas.map((l) => (<><dt key={l.concepto + 't'}>{l.concepto}{l.tipoEfectivoPct != null && <span className="xs muted"> · {fmtNum(l.tipoEfectivoPct, 2)} %</span>}{l.verificado === false && <span className="badge badge--warn"> no verificado</span>}</dt><dd key={l.concepto}>{fmtEUR(l.importe, 0)}</dd></>))}
          <dt className="dl__total">Total gastos</dt><dd className="dl__total">{fmtEUR(r.gastos.totalCliente, 0)}</dd>
        </dl>
        <p className="xs muted mt-2">Aranceles = cota inferior (sin folios, copias ni suplidos). Tasación: supuesto editable de {fmtEUR(pol.tasacionEur)}.</p>
      </Card>
      {(r.avisos.length > 0 || r.supuestos.length > 0) && (
        <div className="callout callout--warn small"><strong>Avisos y supuestos</strong>
          <ul>{[...r.avisos, ...r.supuestos].map((a) => <li key={a}>{a}</li>)}</ul></div>
      )}
    </div>
  );
}
