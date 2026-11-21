/**
 * Fórmulas deterministas del simulador hipotecario (sin modelos, sin decisión de concesión).
 * Port a TypeScript de la implementación de referencia de Banca
 * (reports/audit/04_banca/asesor_v2_reference.py). Validado con vitest contra los valores
 * de referencia de ese informe y, cuando existe, contra artifacts/advisor/test_vectors.json.
 */

// ───────────── 1. Amortización francesa ─────────────
/** Cuota constante: C = P·r / (1 − (1+r)^−n), r = TIN/12. TIN en % anual. */
export function cuotaFrancesa(capital: number, tinAnualPct: number, nMeses: number): number {
  if (capital <= 0 || nMeses <= 0) return 0;
  const r = tinAnualPct / 100 / 12;
  if (Math.abs(r) < 1e-12) return capital / nMeses;
  return (capital * r) / (1 - (1 + r) ** -nMeses);
}

export function saldoFinal(capital: number, tinAnualPct: number, nMeses: number, cuota: number): number {
  const r = tinAnualPct / 100 / 12;
  let s = capital;
  for (let i = 0; i < nMeses; i++) s = s * (1 + r) - cuota;
  return s;
}

/** Inversa: capital que amortiza una cuota dada. */
export function capitalMaximoPorCuota(cuotaMax: number, tinAnualPct: number, nMeses: number): number {
  const r = tinAnualPct / 100 / 12;
  if (Math.abs(r) < 1e-12) return cuotaMax * nMeses;
  return (cuotaMax * (1 - (1 + r) ** -nMeses)) / r;
}

/** Intereses totales pagados a lo largo del préstamo. */
export const interesesTotales = (capital: number, tin: number, n: number) => cuotaFrancesa(capital, tin, n) * n - capital;

// ───────────── 2. Aranceles (RD 1426/1989 notarial, RD 1427/1989 registral), Número 2, rebaja 5 % ─────────────
type Tramo = [number, number];
const TRAMOS_NOTARIA: Tramo[] = [[30050.61, 0.0045], [60101.21, 0.0015], [150253.03, 0.001], [601012.1, 0.0005], [6010121.04, 0.0003]];
const TRAMOS_REGISTRO: Tramo[] = [[30050.61, 0.00175], [60101.21, 0.00125], [150253.03, 0.00075], [601012.1, 0.0003], [Infinity, 0.0002]];

function escala(base: number, fijo: number, umbralFijo: number, tramos: Tramo[]): number {
  let imp = fijo, inf = umbralFijo;
  for (const [sup, tipo] of tramos) {
    if (base <= inf) break;
    imp += (Math.min(base, sup) - inf) * tipo;
    inf = sup;
  }
  return imp;
}

/** Derechos base del arancel notarial (Nº 2) con rebaja del 5 %. No incluye folios, copias ni IVA. */
export function arancelNotarialBase(cuantia: number, prestamoHipotecario = false): number {
  if (cuantia > 6010121.04) throw new RangeError('Por encima de 6.010.121,04 € el arancel es libre');
  let imp = escala(cuantia, 90.151816, 6010.12, TRAMOS_NOTARIA);
  if (prestamoHipotecario) imp *= 0.75;
  return imp * 0.95;
}

/** Derechos base del arancel registral (Nº 2): mín. 24,040484 €, máx. 2.181,673939 €, rebaja 5 %. */
export function arancelRegistralBase(valor: number, prestamoHipotecario = false): number {
  let imp = escala(valor, 24.040484, 6010.12, TRAMOS_REGISTRO);
  if (prestamoHipotecario) imp *= 0.75;
  imp = Math.min(Math.max(imp, 24.040484), 2181.673939);
  return imp * 0.95;
}

// ───────────── 3. Tabla fiscal con vigencias ─────────────
export interface TramoImpuesto { hasta: number; tipoPct: number }
export interface ReglaFiscal {
  ccaa: string;
  impuesto: 'ITP' | 'IVA' | 'IGIC' | 'AJD_compraventa' | string;
  tramos: TramoImpuesto[];
  /** true: escala marginal por tramos; false: tipo único según el valor total */
  progresivo: boolean;
  vigenteDesde: string; // ISO yyyy-mm-dd
  vigenteHasta: string | null;
  fuente: string;
  verificado: boolean;
  tipoVivienda?: string;
  colectivo?: string;
  notas?: string;
}

export function tipoAplicable(regla: ReglaFiscal, valor: number): number {
  if (regla.progresivo) throw new Error('usar cuotaImpuesto para escalas progresivas');
  for (const t of regla.tramos) if (valor <= t.hasta) return t.tipoPct;
  return regla.tramos[regla.tramos.length - 1].tipoPct;
}

export function cuotaImpuesto(regla: ReglaFiscal, valor: number): number {
  if (!regla.progresivo) return (valor * tipoAplicable(regla, valor)) / 100;
  let imp = 0, inf = 0;
  for (const t of regla.tramos) {
    if (valor <= inf) break;
    imp += ((Math.min(valor, t.hasta) - inf) * t.tipoPct) / 100;
    inf = t.hasta;
  }
  return imp;
}

export function reglaVigente(reglas: ReglaFiscal[], ccaa: string, impuesto: string, fecha: string, filtro?: (r: ReglaFiscal) => boolean): ReglaFiscal {
  const cand = reglas.filter((r) => r.ccaa === ccaa && r.impuesto === impuesto && r.vigenteDesde <= fecha
    && (r.vigenteHasta == null || fecha <= r.vigenteHasta) && (!filtro || filtro(r)));
  if (cand.length !== 1) throw new Error(`${cand.length} reglas vigentes para ${ccaa}/${impuesto} en ${fecha}`);
  return cand[0];
}

/** Regla de tipo único (cuando el usuario introduce el tipo a mano). */
export const reglaTipoUnico = (tipoPct: number, impuesto = 'ITP'): ReglaFiscal => ({
  ccaa: '—', impuesto, tramos: [{ hasta: Infinity, tipoPct }], progresivo: false,
  vigenteDesde: '1900-01-01', vigenteHasta: null, fuente: 'Introducido por el usuario', verificado: false,
});

// ───────────── 4. Gastos de compra (lado comprador) ─────────────
/** Ley 5/2019 art. 14.1.e: estos gastos del préstamo corresponden a la entidad. */
export const GASTOS_PRESTAMO_A_CARGO_BANCO = ['Notaría de la escritura de préstamo', 'Registro de la hipoteca', 'Gestoría', 'AJD del préstamo'] as const;

export interface Gastos {
  impuesto: number; ajdCompraventa: number; notariaArancelBase: number; registroArancelBase: number; tasacion: number; total: number;
}
export function gastosCompra(precio: number, reglaImpuesto: ReglaFiscal, tasacion: number, reglaAjd?: ReglaFiscal | null): Gastos {
  const impuesto = cuotaImpuesto(reglaImpuesto, precio);
  const ajdCompraventa = reglaAjd ? cuotaImpuesto(reglaAjd, precio) : 0;
  const notariaArancelBase = arancelNotarialBase(precio);
  const registroArancelBase = arancelRegistralBase(precio);
  return { impuesto, ajdCompraventa, notariaArancelBase, registroArancelBase, tasacion, total: impuesto + ajdCompraventa + notariaArancelBase + registroArancelBase + tasacion };
}

// ───────────── 5. Capacidad de pago con estrés ─────────────
export interface Perfil { ingresosNetosMes: number; deudasMes?: number; edadMayorTitular?: number; ahorro?: number }
export type TipoInteres = 'fijo' | 'variable' | 'mixto';

export function dsti(cuota: number, p: Perfil): number {
  if (p.ingresosNetosMes <= 0) return Infinity;
  return (cuota + (p.deudasMes ?? 0)) / p.ingresosNetosMes;
}

export function plazoMaximoMeses(edad: number, plazoSolicitadoAnios: number, edadMaxVencimiento = 75, plazoMaxAnios = 30): number {
  const anios = Math.min(plazoSolicitadoAnios, plazoMaxAnios, edadMaxVencimiento - edad);
  return Math.max(anios, 0) * 12;
}

export interface Capacidad {
  cuota: number; cuotaEstres: number; dsti: number; dstiEstres: number; ltv: number; lti: number; capitalMaxDsti: number;
  holgura: 'dentro_umbral_orientativo' | 'por_encima_umbral_orientativo';
}
export function simulacionCapacidad(precio: number, capital: number, tinPct: number, nMeses: number, perfil: Perfil,
  tipo: TipoInteres, estresPp = 3, umbralDsti = 0.35): Capacidad {
  const conEstres = tipo === 'variable' || tipo === 'mixto';
  const c = cuotaFrancesa(capital, tinPct, nMeses);
  const cE = conEstres ? cuotaFrancesa(capital, tinPct + estresPp, nMeses) : c;
  const ing = perfil.ingresosNetosMes;
  const r = {
    cuota: c, cuotaEstres: cE, dsti: dsti(c, perfil), dstiEstres: dsti(cE, perfil),
    ltv: precio > 0 ? capital / precio : NaN,
    lti: ing > 0 ? capital / (12 * ing) : Infinity,
    capitalMaxDsti: capitalMaximoPorCuota(Math.max(umbralDsti * ing - (perfil.deudasMes ?? 0), 0), tinPct + (conEstres ? estresPp : 0), nMeses),
  };
  return { ...r, holgura: r.dstiEstres <= umbralDsti ? 'dentro_umbral_orientativo' : 'por_encima_umbral_orientativo' };
}

// ───────────── 6. Simulación completa (lo que usa la interfaz) ─────────────
export interface Politica {
  umbralDsti: number;        // fracción (0,35)
  estresPp: number;          // puntos porcentuales
  edadMaxVencimiento: number;
  plazoMaxAnios: number;
  ltvReferencia: number;     // fracción (0,80)
  tasacion: number;          // €
  fuente?: string;
  ilustrativa?: boolean;
}
/** Parámetros por defecto: propuestos en el informe de Banca (§5.2, §6.3) como ORIENTATIVOS, sin base legal. */
export const POLITICA_POR_DEFECTO: Politica = {
  umbralDsti: 0.35, estresPp: 3, edadMaxVencimiento: 75, plazoMaxAnios: 30, ltvReferencia: 0.8, tasacion: 0,
  fuente: 'reports/audit/04_banca_asesor.md §5.2 (parámetros orientativos propuestos)', ilustrativa: true,
};

export interface EntradaSimulacion {
  precio: number; ahorro: number; ingresosNetosMes: number; deudasMes: number; edad: number; plazoAnios: number;
  tinPct: number; tipo: TipoInteres; reglaImpuesto: ReglaFiscal; reglaAjd?: ReglaFiscal | null;
}
export interface Resultado {
  gastos: Gastos; aportacionNeta: number; capitalNecesario: number; capitalTopeLtv: number; ahorroInsuficiente: number;
  nMeses: number; capacidad: Capacidad; intereses: number; sensibilidad: { deltaPp: number; cuota: number }[];
  avisos: string[];
}

export function simular(e: EntradaSimulacion, pol: Politica = POLITICA_POR_DEFECTO): Resultado {
  const avisos: string[] = [];
  const gastos = gastosCompra(e.precio, e.reglaImpuesto, pol.tasacion, e.reglaAjd);
  const aportacionNeta = e.ahorro - gastos.total;            // ahorro disponible para entrada tras pagar gastos
  const capitalNecesario = Math.max(e.precio - Math.max(aportacionNeta, 0), 0);
  const capitalTopeLtv = pol.ltvReferencia * e.precio;
  const ahorroInsuficiente = Math.max(capitalNecesario - capitalTopeLtv, 0);
  if (aportacionNeta < 0) avisos.push('El ahorro no cubre los gastos de compra estimados.');
  if (ahorroInsuficiente > 0) avisos.push(`El capital necesario supera el ${Math.round(pol.ltvReferencia * 100)} % del precio (LTV de referencia, práctica de mercado, no límite legal).`);
  const nMeses = plazoMaximoMeses(e.edad, e.plazoAnios, pol.edadMaxVencimiento, pol.plazoMaxAnios);
  if (nMeses < e.plazoAnios * 12) avisos.push(`Plazo limitado a ${nMeses / 12} años por la edad máxima al vencimiento de referencia (${pol.edadMaxVencimiento} años; parámetro de política, no límite legal).`);
  if (!e.reglaImpuesto.verificado) avisos.push('El tipo impositivo no está verificado en el boletín oficial: compruebe la normativa vigente de su comunidad autónoma.');
  const capacidad = simulacionCapacidad(e.precio, capitalNecesario, e.tinPct, nMeses,
    { ingresosNetosMes: e.ingresosNetosMes, deudasMes: e.deudasMes }, e.tipo, pol.estresPp, pol.umbralDsti);
  const sensibilidad = [-1, 1, 2, 3].map((d) => ({ deltaPp: d, cuota: cuotaFrancesa(capitalNecesario, Math.max(e.tinPct + d, 0), nMeses) }));
  return {
    gastos, aportacionNeta, capitalNecesario, capitalTopeLtv, ahorroInsuficiente, nMeses, capacidad,
    intereses: nMeses > 0 ? interesesTotales(capitalNecesario, e.tinPct, nMeses) : 0, sensibilidad, avisos,
  };
}
