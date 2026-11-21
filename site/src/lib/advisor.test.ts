/**
 * Tests del simulador. Dos bloques:
 *  A) Valores de referencia publicados por Banca en reports/audit/04_banca/test_asesor_v2_reference.py (24/24 OK en Python).
 *  B) Vectores exportados por Banca en ../artifacts/advisor/test_vectors.json (si el fichero existe).
 *     El formato se interpreta de forma tolerante: lista de casos {fn|function|funcion, args|inputs|input, expected|esperado, tol?}
 *     o un objeto {cases|vectors|casos: [...]}. Cada función se resuelve por su nombre en Python o en TS.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import * as A from './advisor';

const close = (a: number, b: number, tol = 0.01) => expect(Math.abs(a - b)).toBeLessThanOrEqual(tol);

describe('A · Cuota francesa', () => {
  it.each([
    [150000, 3.0, 300, 711.32], [237500, 2.78, 360, 973.35], [200000, 3.5, 360, 898.09], [200000, 6.5, 360, 1264.14], [100000, 0, 120, 833.33],
  ])('P=%d TIN=%d n=%d → %d', (P, tin, n, esp) => close(A.cuotaFrancesa(P, tin, n), esp));
  it('el cuadro termina en saldo 0', () => {
    const c = A.cuotaFrancesa(150000, 3, 300);
    expect(Math.abs(A.saldoFinal(150000, 3, 300, c))).toBeLessThan(1e-6);
  });
  it('capital máximo es la inversa de la cuota', () => {
    const c = A.cuotaFrancesa(180000, 3.2, 300);
    close(A.capitalMaximoPorCuota(c, 3.2, 300), 180000, 1e-4);
  });
});

describe('A · Aranceles base (RD 1426/1989 y 1427/1989, Nº 2, −5 %)', () => {
  it.each([
    [5000, 85.64, 22.84], [100000, 269.14, 126.92], [200000, 340.51, 176.9], [250000, 364.26, 191.15], [400000, 435.51, 233.9],
  ])('base %d', (b, n, r) => { close(A.arancelNotarialBase(b), n); close(A.arancelRegistralBase(b), r); });
  it('máximo registral', () => close(A.arancelRegistralBase(50_000_000), 2181.673939 * 0.95));
});

const REGLAS: A.ReglaFiscal[] = [
  { ccaa: 'X', impuesto: 'ITP', tramos: [{ hasta: Infinity, tipoPct: 10 }], progresivo: false, vigenteDesde: '2020-01-01', vigenteHasta: '2026-05-31', fuente: 'norma A', verificado: false },
  { ccaa: 'X', impuesto: 'ITP', tramos: [{ hasta: 1_000_000, tipoPct: 9 }, { hasta: Infinity, tipoPct: 11 }], progresivo: false, vigenteDesde: '2026-06-01', vigenteHasta: null, fuente: 'norma B', verificado: false },
  { ccaa: 'Y', impuesto: 'ITP', tramos: [{ hasta: 250_000, tipoPct: 8 }, { hasta: Infinity, tipoPct: 10 }], progresivo: true, vigenteDesde: '2020-01-01', vigenteHasta: null, fuente: 'norma C', verificado: false },
];

describe('A · Tabla fiscal con vigencias', () => {
  it('selecciona la regla vigente', () => {
    expect(A.reglaVigente(REGLAS, 'X', 'ITP', '2026-05-31').fuente).toBe('norma A');
    expect(A.reglaVigente(REGLAS, 'X', 'ITP', '2026-06-01').fuente).toBe('norma B');
    expect(() => A.reglaVigente(REGLAS, 'Z', 'ITP', '2026-06-01')).toThrow();
  });
  it('tipo único por valor total y escala progresiva', () => {
    const b = A.reglaVigente(REGLAS, 'X', 'ITP', '2026-07-01');
    close(A.cuotaImpuesto(b, 300_000), 27_000);
    close(A.cuotaImpuesto(b, 1_200_000), 132_000);
    close(A.cuotaImpuesto(A.reglaVigente(REGLAS, 'Y', 'ITP', '2026-07-01'), 300_000), 25_000);
  });
});

describe('A · Gastos y capacidad de pago', () => {
  it('gastos de compra sin conceptos del préstamo', () => {
    const g = A.gastosCompra(200_000, REGLAS[0], 350);
    close(g.total, 20_000 + 340.51 + 176.9 + 350, 0.02);
    expect(A.GASTOS_PRESTAMO_A_CARGO_BANCO).toContain('AJD del préstamo');
  });
  it('estrés en variable, no en fijo; sin estado de concesión', () => {
    const p = { ingresosNetosMes: 3000 };
    const v = A.simulacionCapacidad(250_000, 200_000, 3.5, 360, p, 'variable', 3);
    const f = A.simulacionCapacidad(250_000, 200_000, 3.5, 360, p, 'fijo', 3);
    close(v.dsti, 0.2994, 1e-4); close(v.dstiEstres, 0.4214, 1e-4); close(f.dstiEstres, 0.2994, 1e-4); close(v.ltv, 0.8, 1e-9);
    expect(v.holgura).toBe('por_encima_umbral_orientativo');
    expect(f.holgura).toBe('dentro_umbral_orientativo');
    const txt = JSON.stringify(v).toLowerCase();
    expect(txt).not.toMatch(/aprobad|denegad|approved|denied|status/);
  });
  it('la cuota usa el tipo mostrado', () => close(A.simulacionCapacidad(250_000, 200_000, 3.5, 360, { ingresosNetosMes: 3000 }, 'fijo').cuota, A.cuotaFrancesa(200_000, 3.5, 360), 1e-9));
  it('ingresos 0 → DSTI infinito', () => expect(A.simulacionCapacidad(250_000, 200_000, 3.5, 360, { ingresosNetosMes: 0 }, 'fijo').dsti).toBe(Infinity));
  it.each([[40, 30, 360], [60, 30, 180], [76, 30, 0], [50, 20, 240]])('plazo por edad %d/%d → %d', (e, s, m) => expect(A.plazoMaximoMeses(e, s)).toBe(m));
  it('simular(): ninguna salida contiene "aprobada/denegada"', () => {
    const r = A.simular({ precio: 250_000, ahorro: 60_000, ingresosNetosMes: 3000, deudasMes: 0, edad: 35, plazoAnios: 30, tinPct: 3.5, tipo: 'variable', reglaImpuesto: A.reglaTipoUnico(10) });
    expect(JSON.stringify(r).toLowerCase()).not.toMatch(/aprobad|denegad|approved|denied/);
    close(r.capacidad.cuota, A.cuotaFrancesa(r.capitalNecesario, 3.5, 360), 1e-9);
  });
});

// ───────────── B · Vectores de Banca ─────────────
const VECTORS = path.resolve(__dirname, '../../../artifacts/advisor/test_vectors.json');
const hasVectors = fs.existsSync(VECTORS);

type Case = Record<string, unknown>;
function loadCases(): Case[] {
  const raw = JSON.parse(fs.readFileSync(VECTORS, 'utf8'));
  if (Array.isArray(raw)) return raw;
  for (const k of ['cases', 'vectors', 'casos', 'tests']) if (Array.isArray(raw[k])) return raw[k];
  // {funcion: [casos]}
  const out: Case[] = [];
  for (const [fn, list] of Object.entries(raw)) if (Array.isArray(list)) for (const c of list as Case[]) out.push({ fn, ...c });
  return out;
}

const g = (o: Case, ...ks: string[]) => { for (const k of ks) if (o[k] !== undefined) return o[k]; return undefined; };
const num = (v: unknown) => (v === 'inf' || v === 'Infinity' || v === null ? Infinity : Number(v));

function toRegla(r: Case): A.ReglaFiscal {
  const tramosRaw = (g(r, 'tramos') as Case[] | undefined) ?? [{ hasta: null, tipo_pct: g(r, 'tipo_pct', 'tipoPct') }];
  return {
    ccaa: String(g(r, 'ccaa', 'ccaa_code') ?? ''), impuesto: String(g(r, 'impuesto') ?? 'ITP'),
    tramos: tramosRaw.map((t) => ({ hasta: num(g(t, 'hasta', 'tramo_hasta')), tipoPct: Number(g(t, 'tipo_pct', 'tipoPct', 'tipo')) })),
    progresivo: Boolean(g(r, 'progresivo') ?? (g(r, 'modo') === 'marginal')),
    vigenteDesde: String(g(r, 'vigente_desde', 'vigenteDesde') ?? '1900-01-01'), vigenteHasta: (g(r, 'vigente_hasta', 'vigenteHasta') as string) ?? null,
    fuente: String(g(r, 'fuente', 'norma') ?? ''), verificado: Boolean(g(r, 'verificado')),
  };
}

const FNS: Record<string, (a: Case) => unknown> = {
  cuota_francesa: (a) => A.cuotaFrancesa(num(g(a, 'capital', 'P', 'principal')), num(g(a, 'tin_anual_pct', 'tin', 'tin_pct')), num(g(a, 'n_meses', 'n'))),
  capital_maximo_por_cuota: (a) => A.capitalMaximoPorCuota(num(g(a, 'cuota_max', 'cuota')), num(g(a, 'tin_anual_pct', 'tin', 'tin_pct')), num(g(a, 'n_meses', 'n'))),
  arancel_notarial_base: (a) => A.arancelNotarialBase(num(g(a, 'cuantia', 'base', 'valor', 'precio')), Boolean(g(a, 'prestamo_hipotecario'))),
  arancel_registral_base: (a) => A.arancelRegistralBase(num(g(a, 'valor', 'base', 'cuantia', 'precio')), Boolean(g(a, 'prestamo_hipotecario'))),
  plazo_maximo_meses: (a) => A.plazoMaximoMeses(num(g(a, 'edad')), num(g(a, 'plazo_solicitado_anios', 'plazo_anios', 'plazo')), a.edad_max_vencimiento != null ? num(a.edad_max_vencimiento) : undefined, a.plazo_max_anios != null ? num(a.plazo_max_anios) : undefined),
  cuota_impuesto: (a) => A.cuotaImpuesto(toRegla((g(a, 'regla') as Case) ?? a), num(g(a, 'valor', 'precio'))),
  gastos_compra: (a) => {
    const r = A.gastosCompra(num(g(a, 'precio')), toRegla((g(a, 'regla_impuesto', 'regla') as Case) ?? a), num(g(a, 'tasacion') ?? 0), g(a, 'regla_ajd') ? toRegla(g(a, 'regla_ajd') as Case) : null);
    return { impuesto: r.impuesto, ajd_compraventa: r.ajdCompraventa, notaria_arancel_base: r.notariaArancelBase, registro_arancel_base: r.registroArancelBase, tasacion: r.tasacion, total: r.total };
  },
  simulacion_capacidad: (a) => {
    const perfil = (g(a, 'perfil') as Case) ?? a;
    const r = A.simulacionCapacidad(num(g(a, 'precio')), num(g(a, 'capital')), num(g(a, 'tin_pct', 'tin')), num(g(a, 'n_meses', 'n')),
      { ingresosNetosMes: num(g(perfil, 'ingresos_netos_mes', 'ingresos')), deudasMes: num(g(perfil, 'deudas_mes') ?? 0) },
      String(g(a, 'tipo') ?? 'fijo') as A.TipoInteres, num(g(a, 'estres_pp') ?? 3), num(g(a, 'umbral_dsti') ?? 0.35));
    return { cuota: r.cuota, cuota_estres: r.cuotaEstres, dsti: r.dsti, dsti_estres: r.dstiEstres, ltv: r.ltv, lti: r.lti, capital_max_dsti: r.capitalMaxDsti, holgura: r.holgura };
  },
};
const ALIASES: Record<string, string> = { cuotaFrancesa: 'cuota_francesa', capitalMaximoPorCuota: 'capital_maximo_por_cuota', arancelNotarialBase: 'arancel_notarial_base', arancelRegistralBase: 'arancel_registral_base', plazoMaximoMeses: 'plazo_maximo_meses', cuotaImpuesto: 'cuota_impuesto', gastosCompra: 'gastos_compra', simulacionCapacidad: 'simulacion_capacidad' };

function compare(got: unknown, exp: unknown, tol: number, where: string) {
  if (typeof exp === 'number' || exp === 'inf' || exp === 'Infinity') {
    const e = num(exp);
    if (!Number.isFinite(e)) { expect(got, where).toBe(Infinity); return; }
    expect(Math.abs(Number(got) - e), `${where}: ${got} vs ${e}`).toBeLessThanOrEqual(tol);
  } else if (exp && typeof exp === 'object' && !Array.isArray(exp)) {
    for (const [k, v] of Object.entries(exp)) compare((got as Case)?.[k], v, tol, `${where}.${k}`);
  } else expect(got, where).toEqual(exp);
}

describe.skipIf(!hasVectors)('B · Vectores de Banca (artifacts/advisor/test_vectors.json)', () => {
  const cases = hasVectors ? loadCases() : [];
  it('el fichero contiene casos', () => expect(cases.length).toBeGreaterThan(0));
  cases.forEach((c, i) => {
    const fnName = String(g(c, 'fn', 'function', 'funcion', 'func') ?? '');
    const key = ALIASES[fnName] ?? fnName;
    const args = (g(c, 'args', 'inputs', 'input', 'entrada', 'kwargs') as Case) ?? c;
    const expected = g(c, 'expected', 'esperado', 'output', 'salida');
    const tol = Number(g(c, 'tol', 'abs_tol', 'tolerance') ?? 0.01);
    const name = String(g(c, 'id', 'name', 'nombre') ?? `caso ${i}`);
    const impl = FNS[key];
    it.skipIf(!impl)(`${name} · ${fnName}`, () => compare(impl!(args), expected, tol, name));
  });
});
