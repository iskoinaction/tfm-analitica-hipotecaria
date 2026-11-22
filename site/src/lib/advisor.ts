/**
 * Simulador hipotecario determinista (sin modelos, sin decisión de concesión).
 * Port a TypeScript del motor Python src/advisor (engine.py, fiscal.py, amortization.py).
 * Validado con vitest contra artifacts/advisor/test_vectors.json.
 */

// ───────────── Amortización francesa ─────────────
export function cuotaFrancesa(capital: number, tinPct: number, n: number): number {
  if (capital <= 0 || n <= 0) return 0;
  const r = tinPct / 100 / 12;
  if (Math.abs(r) < 1e-12) return capital / n;
  return (capital * r) / (1 - (1 + r) ** -n);
}
export function saldoTras(capital: number, tinPct: number, cuota: number, meses: number): number {
  const r = tinPct / 100 / 12;
  if (Math.abs(r) < 1e-12) return Math.max(capital - cuota * meses, 0);
  const f = (1 + r) ** meses;
  return Math.max(capital * f - (cuota * (f - 1)) / r, 0);
}
export function capitalMaximoPorCuota(cuotaMax: number, tinPct: number, n: number): number {
  if (cuotaMax <= 0 || n <= 0) return 0;
  const r = tinPct / 100 / 12;
  if (Math.abs(r) < 1e-12) return cuotaMax * n;
  return (cuotaMax * (1 - (1 + r) ** -n)) / r;
}
const r2 = (x: number) => Math.round((x + Number.EPSILON) * 100) / 100;

export interface FilaCuadro { anio: number; cuota: number; tin: number; pagado: number; intereses: number; amortizacion: number; saldo: number }
/** Cuadro anual; tramos = [meses, TIN%]; la cuota se recalcula al inicio de cada tramo. */
export function cuadroAnual(capital: number, tramos: [number, number][]): FilaCuadro[] {
  const nTot = tramos.reduce((a, [m]) => a + m, 0);
  const filas: FilaCuadro[] = [];
  let saldo = capital, mes = 0, cuota = 0;
  let acc = { c: 0, i: 0, a: 0 };
  for (const [meses, tin] of tramos) {
    cuota = cuotaFrancesa(saldo, tin, nTot - mes);
    const r = tin / 100 / 12;
    for (let k = 0; k < meses; k++) {
      const interes = saldo * r;
      const amort = Math.min(cuota - interes, saldo);
      saldo -= amort; mes++;
      acc = { c: acc.c + interes + amort, i: acc.i + interes, a: acc.a + amort };
      if (mes % 12 === 0 || mes === nTot) {
        filas.push({ anio: Math.floor((mes - 1) / 12) + 1, cuota: r2(cuota), tin, pagado: r2(acc.c), intereses: r2(acc.i), amortizacion: r2(acc.a), saldo: r2(Math.max(saldo, 0)) });
        acc = { c: 0, i: 0, a: 0 };
      }
    }
  }
  return filas;
}

// ───────────── Tabla fiscal (artifacts/advisor/fiscal_tables.json) ─────────────
export interface TramoJSON { desde: number; hasta: number | null; tipo_pct: number }
export interface Regla {
  id: string; ccaa_code: string; impuesto: string; ambito: string; condicion: string; modo: 'unico_por_valor' | 'marginal' | string;
  tramos: TramoJSON[]; vigente_desde: string | null; vigente_hasta: string | null; norma: string; articulo?: string;
  url_fuente?: string; verificado: boolean; notas?: string;
}
interface Escala { cuota_fija_hasta: { limite: number; importe: number }; tramos: { hasta: number | null; por_mil: number }[]; limite_superior_regulado: number | null; minimo: number | null; maximo: number | null; reduccion_prestamo_hipotecario_factor: number; rebaja_general_pct: number; norma?: string; url_fuente?: string; verificado?: boolean }
export interface Aranceles { notaria: Escala; registro: Escala }

export function reglaVigente(reglas: Regla[], ccaa: string, impuesto: string, ambito: string, fecha: string, condiciones: string[] = []): Regla | null {
  const cond = new Set([...condiciones, 'general']);
  const cand = reglas.filter((r) => r.impuesto === impuesto && r.ambito === ambito && (r.ccaa_code === ccaa || r.ccaa_code === '*') && cond.has(r.condicion)
    && (!r.vigente_desde || fecha >= r.vigente_desde) && (!r.vigente_hasta || fecha <= r.vigente_hasta));
  if (!cand.length) return null;
  cand.sort((a, b) => Number(a.ccaa_code === '*') - Number(b.ccaa_code === '*') || Number(a.condicion === 'general') - Number(b.condicion === 'general'));
  return cand[0];
}
export function cuotaImpuesto(r: Regla, base: number): number {
  if (!r.tramos.length) throw new Error(`Regla ${r.id} no modelada`);
  if (base <= 0) return 0;
  const hasta = (t: TramoJSON) => (t.hasta == null ? Infinity : t.hasta);
  if (r.modo === 'unico_por_valor') {
    for (const t of r.tramos) if (base <= hasta(t)) return (base * t.tipo_pct) / 100;
    return (base * r.tramos[r.tramos.length - 1].tipo_pct) / 100;
  }
  let tot = 0;
  for (const t of r.tramos) { if (base <= t.desde) break; tot += ((Math.min(base, hasta(t)) - t.desde) * t.tipo_pct) / 100; }
  return tot;
}
export const tipoEfectivoPct = (r: Regla, base: number) => (base > 0 ? (cuotaImpuesto(r, base) / base) * 100 : 0);

function escalaArancel(base: number, c: Escala): number {
  let imp = c.cuota_fija_hasta.importe, inf = c.cuota_fija_hasta.limite;
  for (const t of c.tramos) {
    const sup = t.hasta == null ? Infinity : t.hasta;
    if (base <= inf) break;
    imp += ((Math.min(base, sup) - inf) * t.por_mil) / 1000;
    inf = sup;
  }
  return imp;
}
export function arancel(c: Escala, base: number, prestamoHipotecario = false): number {
  if (c.limite_superior_regulado && base > c.limite_superior_regulado) throw new RangeError('Base por encima del máximo regulado del arancel');
  let imp = escalaArancel(base, c);
  if (prestamoHipotecario) imp *= c.reduccion_prestamo_hipotecario_factor;
  if (c.minimo != null) imp = Math.max(imp, c.minimo);
  if (c.maximo != null) imp = Math.min(imp, c.maximo);
  return imp * (1 - c.rebaja_general_pct / 100);
}

// ───────────── Política (data/metadata/advisor_policy.yaml; valores ILUSTRATIVOS) ─────────────
export interface Politica {
  dstiRef: number; dstiAlto: number; estresPp: number; estresAplicaA: string[]; edadMax: number; plazoMax: number; ltvRef: number; ltiRef: number; tasacionEur: number; gestoriaEur: number;
}
export const POLITICA_POR_DEFECTO: Politica = { dstiRef: 0.35, dstiAlto: 0.4, estresPp: 3, estresAplicaA: ['variable', 'mixto'], edadMax: 75, plazoMax: 30, ltvRef: 0.8, ltiRef: 6, tasacionEur: 400, gestoriaEur: 0 };
export function politicaDe(j: Record<string, any> | undefined | null): Politica { // eslint-disable-line @typescript-eslint/no-explicit-any
  if (!j) return POLITICA_POR_DEFECTO;
  const d = POLITICA_POR_DEFECTO;
  return {
    dstiRef: j.dsti?.referencia ?? d.dstiRef, dstiAlto: j.dsti?.esfuerzo_elevado ?? d.dstiAlto, estresPp: j.estres?.incremento_tipo_pp ?? d.estresPp,
    estresAplicaA: j.estres?.aplica_a ?? d.estresAplicaA, edadMax: j.edad?.maxima_al_vencimiento ?? d.edadMax, plazoMax: j.plazo?.maximo_anios ?? d.plazoMax,
    ltvRef: j.ltv?.referencia ?? d.ltvRef, ltiRef: j.lti?.referencia ?? d.ltiRef, tasacionEur: j.gastos_supuestos?.tasacion_eur ?? d.tasacionEur, gestoriaEur: j.gastos_supuestos?.gestoria_compraventa_eur ?? d.gestoriaEur,
  };
}

// ───────────── Simulación ─────────────
export type Modalidad = 'fijo' | 'variable' | 'mixto';
export interface Entrada {
  ccaa: string; precio: number; tipoVivienda: 'usada' | 'nueva'; viviendaHabitual: boolean; aportacion: number; valorTasacion?: number | null;
  ingresosNetosMes: number; numeroPagas?: 12 | 14; otrasDeudasMes?: number; edad: number; plazoAnios: number; modalidad: Modalidad;
  tinPct: number; tinVariablePct?: number | null; aniosFijos?: number; fecha: string; gastosTasacion?: number; gestoria?: number;
}
export interface LineaGasto { concepto: string; importe: number; aCargo: 'cliente'; norma?: string; url?: string; verificado?: boolean; tipoEfectivoPct?: number | null; nota?: string }
export type Semaforo = 'verde' | 'ambar' | 'rojo';
export interface Resultado {
  gastos: { lineas: LineaGasto[]; totalCliente: number };
  capital: number; entradaNecesariaLtv: number; ltv: number | null; lti: number | null; plazoAnios: number; plazoMeses: number;
  cuota: number; cuotaEstres: number; cuotaTrasFijo: number | null; totalIntereses: number; totalPagado: number; cuadro: FilaCuadro[];
  ingresosEq: number; dsti: number | null; dstiEstres: number | null; estresAplicado: boolean; capitalMaxDsti: number;
  semaforo: Semaforo; motivo: string; avisos: string[]; supuestos: string[];
}

export function simular(e: Entrada, reglas: Regla[], ar: Aranceles, pol: Politica = POLITICA_POR_DEFECTO): Resultado {
  const avisos: string[] = [], supuestos: string[] = [];
  const cond = e.viviendaHabitual ? ['vivienda_habitual'] : [];
  const lineas: LineaGasto[] = [];
  const reg = (concepto: string, r: Regla, base: number): LineaGasto => ({
    concepto, importe: r2(cuotaImpuesto(r, base)), aCargo: 'cliente', tipoEfectivoPct: r2(tipoEfectivoPct(r, base) * 100) / 100,
    norma: r.articulo ? `${r.norma}, art. ${r.articulo}` : r.norma, url: r.url_fuente, verificado: r.verificado,
  });
  if (e.tipoVivienda === 'usada') {
    const r = reglaVigente(reglas, e.ccaa, 'ITP', 'vivienda_usada', e.fecha, cond);
    if (!r) avisos.push('No hay regla de ITP vigente para la fecha indicada: impuesto no calculado.');
    else lineas.push(reg('ITP (transmisiones patrimoniales onerosas)', r, e.precio));
  } else {
    let ind: Regla | null = null;
    for (const imp of ['IGIC', 'IPSI', 'IVA']) { ind = reglaVigente(reglas, e.ccaa, imp, 'vivienda_nueva', e.fecha, cond); if (ind) break; }
    if (!ind || !ind.tramos.length) avisos.push(`Impuesto indirecto de la vivienda nueva NO MODELADO en este territorio (${ind?.impuesto ?? 'sin regla'}): el total de gastos lo excluye.`);
    else lineas.push(reg(`${ind.impuesto} vivienda nueva`, ind, e.precio));
    const r = reglaVigente(reglas, e.ccaa, 'AJD', 'vivienda_nueva', e.fecha, cond);
    if (!r) avisos.push('No hay regla de AJD vigente para la fecha indicada: impuesto no calculado.');
    else lineas.push(reg('AJD (escritura de compraventa)', r, e.precio));
  }
  const iva = reglaVigente(reglas, e.ccaa, 'IVA_honorarios', 'aranceles', e.fecha);
  const fueraIva = ['05', '18', '19'].includes(e.ccaa);
  const ivaPct = iva && !fueraIva ? iva.tramos[0].tipo_pct : 0;
  for (const [esc, nombre] of [[ar.notaria, 'Notaría compraventa (arancel base)'], [ar.registro, 'Registro de la Propiedad compraventa (arancel base)']] as const) {
    const b = arancel(esc, e.precio);
    lineas.push({ concepto: nombre, importe: r2(b * (1 + ivaPct / 100)), aCargo: 'cliente', norma: esc.norma, url: esc.url_fuente, verificado: esc.verificado, nota: 'Cota inferior: no incluye folios, copias ni suplidos' });
  }
  if (fueraIva) avisos.push('Fuera del territorio IVA no se suma IVA a los aranceles (IGIC/IPSI no modelados).');
  lineas.push({ concepto: 'Tasación (a cargo del cliente, Ley 5/2019 art. 14.1.e)', importe: e.gastosTasacion ?? pol.tasacionEur, aCargo: 'cliente', verificado: true, nota: 'importe = supuesto editable' });
  if (e.gestoria ?? pol.gestoriaEur) lineas.push({ concepto: 'Gestoría de la compraventa (opcional)', importe: e.gestoria ?? pol.gestoriaEur, aCargo: 'cliente', nota: 'supuesto editable' });
  for (const l of lineas) if (l.verificado === false) avisos.push(`'${l.concepto}': tipo NO VERIFICADO en boletín oficial (${l.norma}). Use el resultado con cautela.`);
  const totalCliente = r2(lineas.reduce((a, l) => a + l.importe, 0));

  const tasacion = e.valorTasacion ?? e.precio;
  if (e.valorTasacion == null) supuestos.push('Valor de tasación = precio (no indicado).');
  const baseGarantia = Math.min(e.precio, tasacion);
  const capital = Math.max(e.precio + totalCliente - e.aportacion, 0);
  const entradaNecesariaLtv = Math.max(e.precio + totalCliente - pol.ltvRef * baseGarantia, 0);
  const pagas = e.numeroPagas ?? 12;
  const ingresos = (e.ingresosNetosMes * pagas) / 12;
  if (pagas === 14) supuestos.push('Ingresos mensuales indicados por paga; se prorratean 14 pagas en 12 meses.');
  const ltv = baseGarantia ? capital / baseGarantia : null;
  const lti = ingresos > 0 ? capital / (12 * ingresos) : null;
  const plazoMaxEdad = Math.min(pol.plazoMax, pol.edadMax - e.edad);
  let plazo = e.plazoAnios;
  if (plazo > pol.plazoMax) avisos.push(`Plazo solicitado superior al máximo ilustrativo (${pol.plazoMax} años): se mantiene, revise.`);
  if (e.edad + plazo > pol.edadMax) {
    if (plazoMaxEdad >= 1) { avisos.push(`Con ${e.edad} años y ${plazo} años de plazo se superarían los ${pol.edadMax} años al vencimiento (práctica de mercado, no límite legal): se simula con ${plazoMaxEdad} años.`); plazo = plazoMaxEdad; }
    else avisos.push(`La edad supera la referencia de ${pol.edadMax} años al vencimiento (práctica de mercado): se simula con el plazo solicitado, pero es poco habitual en el mercado.`);
  }
  const n = plazo * 12;
  const tinV = e.tinVariablePct ?? e.tinPct;
  const est = pol.estresPp;
  let tramos: [number, number][], cuota: number, cuotaEstres: number, cuotaTrasFijo: number | null = null;
  if (e.modalidad === 'mixto') {
    const nf = Math.min((e.aniosFijos ?? 5) * 12, n);
    tramos = n > nf ? [[nf, e.tinPct], [n - nf, tinV]] : [[n, e.tinPct]];
    cuota = cuotaFrancesa(capital, e.tinPct, n);
    const saldo = saldoTras(capital, e.tinPct, cuota, nf);
    cuotaTrasFijo = n > nf ? cuotaFrancesa(saldo, tinV, n - nf) : cuota;
    cuotaEstres = n > nf ? cuotaFrancesa(saldo, tinV + est, n - nf) : cuota;
  } else {
    tramos = [[n, e.tinPct]];
    cuota = cuotaFrancesa(capital, e.tinPct, n);
    cuotaEstres = e.modalidad === 'variable' ? cuotaFrancesa(capital, e.tinPct + est, n) : cuota;
  }
  const cuadro = capital > 0 && n > 0 ? cuadroAnual(capital, tramos) : [];
  const totalIntereses = r2(cuadro.reduce((a, f) => a + f.intereses, 0));
  const deudas = e.otrasDeudasMes ?? 0;
  const dsti = ingresos > 0 ? (cuota + deudas) / ingresos : null;
  const dstiEstres = ingresos > 0 ? (cuotaEstres + deudas) / ingresos : null;
  const estresAplicado = pol.estresAplicaA.includes(e.modalidad);
  const dEval = estresAplicado ? dstiEstres : dsti;
  const pc = (x: number) => `${(x * 100).toFixed(1).replace('.', ',')} %`;
  let semaforo: Semaforo, motivo: string;
  const con = estresAplicado ? ' con estrés' : '';
  if (dEval == null) { semaforo = 'rojo'; motivo = 'Ingresos nulos: no es posible calcular el esfuerzo.'; }
  else if (dEval > pol.dstiAlto) { semaforo = 'rojo'; motivo = `Esfuerzo elevado: DSTI${con} ${pc(dEval)} > ${Math.round(pol.dstiAlto * 100)} % (umbral ilustrativo).`; }
  else if (dEval > pol.dstiRef) { semaforo = 'ambar'; motivo = `Esfuerzo por encima de la referencia: DSTI${con} ${pc(dEval)} entre ${Math.round(pol.dstiRef * 100)} % y ${Math.round(pol.dstiAlto * 100)} %.`; }
  else { semaforo = 'verde'; motivo = `Esfuerzo dentro de la referencia ilustrativa: DSTI${con} ${pc(dEval)} ≤ ${Math.round(pol.dstiRef * 100)} %.`; }
  if (ltv != null && ltv > pol.ltvRef) avisos.push(`LTV ${pc(ltv)} > ${Math.round(pol.ltvRef * 100)} % (referencia de mercado sobre min(precio, tasación)): la financiación por encima suele requerir garantías adicionales.`);
  if (lti != null && lti > pol.ltiRef) avisos.push(`LTI ${lti.toFixed(1).replace('.', ',')} veces los ingresos netos anuales > ${pol.ltiRef} (orientativo).`);
  if (e.aportacion < totalCliente) avisos.push('La aportación no cubre los gastos de compra: las entidades no suelen financiarlos.');
  if (capital === 0) avisos.push('La aportación cubre el precio y los gastos: no se necesita préstamo.');
  const cuotaMax = Math.max(pol.dstiRef * ingresos - deudas, 0);
  const capitalMaxDsti = capitalMaximoPorCuota(cuotaMax, estresAplicado ? (e.modalidad === 'mixto' ? tinV : e.tinPct) + est : e.tinPct, n);
  return {
    gastos: { lineas, totalCliente }, capital: r2(capital), entradaNecesariaLtv: r2(entradaNecesariaLtv), ltv, lti, plazoAnios: plazo, plazoMeses: n,
    cuota: r2(cuota), cuotaEstres: r2(cuotaEstres), cuotaTrasFijo: cuotaTrasFijo == null ? null : r2(cuotaTrasFijo), totalIntereses, totalPagado: r2(totalIntereses + capital), cuadro,
    ingresosEq: r2(ingresos), dsti, dstiEstres, estresAplicado, capitalMaxDsti: r2(capitalMaxDsti), semaforo, motivo, avisos, supuestos,
  };
}

export const AVISOS_LEGALES = [
  'Simulación orientativa con fines académicos (Atalaya · Analítica Hipotecaria). No es una oferta vinculante, ni una evaluación de solvencia, ni asesoramiento financiero, ni un scoring.',
  'El tipo de interés es el que usted introduce (por defecto, una media de mercado del BCE): no es el precio que ofrecería una entidad concreta.',
  'Los umbrales de esfuerzo (DSTI), LTV, LTI, el estrés de tipos y la edad máxima son parámetros ILUSTRATIVOS y configurables; no son límites legales.',
  'Los gastos de notaría y registro de la escritura de préstamo, la gestoría y el AJD del préstamo corresponden a la entidad (Ley 5/2019, art. 14.1.e). La tasación corre a cargo del cliente.',
  'Los impuestos dependen de la comunidad autónoma y de circunstancias personales; los tipos reducidos no se aplican automáticamente. Compruebe la normativa vigente.',
];
