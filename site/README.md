# Atalaya · Analítica Hipotecaria — web de presentación del TFM

Sitio estático (Vite + React + TypeScript) que presenta el TFM: arquitectura de datos, fuentes, panel provincial (mapa coroplético),
análisis económico, econometría, machine learning (rolling-origin frente a benchmarks), proyecciones 2026-2030 con intervalos,
un simulador hipotecario determinista, la aplicación bancaria, resultados, limitaciones y documentación, más la vista
`#estado` («Estado de las fuentes y del pipeline»).

**Principio:** ninguna cifra se escribe a mano. `scripts/sync-data.mjs` copia y reduce los ficheros reales del repositorio
(`../artifacts/**`, `../data/metadata/**`, `../data/processed/*`, `../data/forecasts/*`, GeoJSON de `../Web/atalaya/static/geo/`)
a `public/data/`. Si un artefacto falta, la sección muestra «Pendiente de generar». El precio por m² es solo MIVAU
(`precio_m2_mivau_tasado`); cualquier serie de Tinsa se excluye en la sincronización (sus condiciones de uso lo prohíben).

## Uso local

```bash
cd site
npm ci
npm run build        # sincroniza datos + tsc + vite build  -> dist/
npm test             # vitest: simulador JS vs artifacts/advisor/test_vectors.json (18 casos del motor Python)
npm run dev          # desarrollo (sincroniza y arranca Vite)
npm run sync-data    # solo sincronizar datos (tras regenerar artefactos)
```

Capturas y comprobación de consola/scroll horizontal (Playwright no es dependencia del proyecto):

```bash
npm run build
PLAYWRIGHT_PATH=/ruta/a/node_modules CHROME_PATH=/ruta/a/chrome npm run screenshots   # -> docs/screenshots/*.jpg
```

## Despliegue en Vercel

1. Importar el repositorio en Vercel con **Root Directory = `site`** (el build necesita acceso a `../artifacts`, `../data`, `../Web`,
   por lo que debe estar activada la opción «Include source files outside of the Root Directory»).
2. `vercel.json` ya define framework Vite, `npm ci`, `npm run build` y salida `dist/`, además de cabeceras de seguridad.
3. Variables de entorno opcionales (Project Settings → Environment Variables):
   - `VITE_APP_URL`: URL de la aplicación bancaria (botón de la sección 11).
   - `VITE_REPO_URL` / `VITE_REPO_BRANCH`: base de los enlaces a la documentación (por defecto, remoto `origin` y rama actual).
4. Alternativa sin acceso al repo padre: ejecutar `npm run build` en local y desplegar `site/` con `public/data/` ya sincronizado
   (si el repo padre no está disponible, `sync-data` conserva el contenido previo de `public/data/`).

Este README no afirma que la web esté desplegada: el despliegue queda pendiente de la cuenta de Vercel del autor.

## Notas

- Accesibilidad: contraste AA, foco visible, navegación por teclado, tablas con `caption`/`scope`, `prefers-reduced-motion` y tema claro/oscuro.
- El simulador no emite «aprobada/denegada»: muestra un indicador de esfuerzo con umbrales ilustrativos y avisos de que no es asesoramiento ni scoring.
- Dependencias fijadas (versiones exactas en `package.json` y `package-lock.json`).
