/* Mapa coroplético provincial en SVG (sin librerías). Unión por código INE (cod_prov).
   Proyección equirectangular corregida por latitud; Canarias desplazada a un recuadro. */
(function () {
  "use strict";
  var A = window.Atalaya;
  var NS = "http://www.w3.org/2000/svg";
  var GEO_URL = "/static/geo/provincias.min.geojson";
  var geoPromise = null;
  var names = {};
  var CANARIAS = { "35": true, "38": true };
  var SHIFT = [5.5, 7.0];         // desplazamiento (lon, lat) del recuadro de Canarias
  var K = Math.cos(40 * Math.PI / 180);

  function loadGeo(url) {
    if (!geoPromise) {
      geoPromise = fetch(url || GEO_URL, { credentials: "same-origin" }).then(function (r) {
        if (!r.ok) throw new Error("GeoJSON no disponible");
        return r.json();
      }).then(function (g) {
        g.features.forEach(function (f) { names[f.properties.cod_prov] = f.properties.name; });
        return g;
      });
    }
    return geoPromise;
  }

  function project(code, pt) {
    var lon = pt[0], lat = pt[1];
    if (CANARIAS[code]) { lon += SHIFT[0]; lat += SHIFT[1]; }
    return [lon * K, -lat];
  }

  function pathData(code, geom) {
    var polys = geom.type === "Polygon" ? [geom.coordinates] : geom.coordinates;
    var d = [];
    polys.forEach(function (poly) {
      poly.forEach(function (ring) {
        ring.forEach(function (pt, i) {
          var p = project(code, pt);
          d.push((i ? "L" : "M") + p[0].toFixed(3) + " " + p[1].toFixed(3));
        });
        d.push("Z");
      });
    });
    return d.join("");
  }

  function quantileBreaks(values, k) {
    var v = values.filter(function (x) { return typeof x === "number" && isFinite(x); }).sort(function (a, b) { return a - b; });
    if (!v.length) return [];
    var br = [];
    for (var i = 1; i < k; i++) br.push(v[Math.min(v.length - 1, Math.floor(i * v.length / k))]);
    return br.filter(function (x, i, arr) { return i === 0 || x !== arr[i - 1]; });
  }

  function classOf(v, breaks) {
    var c = 0;
    while (c < breaks.length && v >= breaks[c]) c++;
    return c;
  }

  function svgEl(tag, attrs) {
    var n = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    return n;
  }

  function render(container, values, opts) {
    opts = opts || {};
    A.clear(container);
    container.appendChild(A.el("div", { class: "skeleton", "aria-hidden": "true" }));
    return loadGeo(opts.geojson).then(function (g) {
      A.clear(container);
      var palette = ["--seq-200", "--seq-300", "--seq-400", "--seq-500", "--seq-600"].map(function (n) { return A.cssVar(n, "#3987e5"); });
      var breaks = quantileBreaks(Object.keys(values).map(function (k) { return values[k]; }), palette.length);
      var colors = palette.slice(palette.length - (breaks.length + 1));
      var svg = svgEl("svg", { role: "img", "aria-label": (opts.label || "Mapa provincial") + (opts.period ? ", " + A.period(opts.period) : "") });
      var defs = svgEl("defs");
      var pat = svgEl("pattern", { id: "hatch-nodata", width: "0.12", height: "0.12", patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" });
      pat.appendChild(svgEl("rect", { width: "0.12", height: "0.12", fill: A.cssVar("--map-nodata", "#e3e8ee") }));
      pat.appendChild(svgEl("line", { x1: "0", y1: "0", x2: "0", y2: "0.12", stroke: A.cssVar("--surface-1", "#fff"), "stroke-width": "0.05" }));
      defs.appendChild(pat);
      svg.appendChild(defs);
      var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      var canBox = [Infinity, Infinity, -Infinity, -Infinity];
      g.features.forEach(function (f) {
        var code = f.properties.cod_prov;
        var v = values[code];
        var has = typeof v === "number" && isFinite(v);
        var p = svgEl("path", { d: pathData(code, f.geometry), fill: has ? colors[classOf(v, breaks)] : "url(#hatch-nodata)" });
        var t = svgEl("title");
        t.textContent = f.properties.name + ": " + (has ? A.fmt(v) + (opts.unit ? " " + opts.unit : "") : "sin dato");
        p.appendChild(t);
        svg.appendChild(p);
        (f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates).forEach(function (poly) {
          poly[0].forEach(function (pt) {
            var q = project(code, pt);
            minX = Math.min(minX, q[0]); maxX = Math.max(maxX, q[0]); minY = Math.min(minY, q[1]); maxY = Math.max(maxY, q[1]);
            if (CANARIAS[code]) { canBox[0] = Math.min(canBox[0], q[0]); canBox[1] = Math.min(canBox[1], q[1]); canBox[2] = Math.max(canBox[2], q[0]); canBox[3] = Math.max(canBox[3], q[1]); }
          });
        });
      });
      if (isFinite(canBox[0])) {
        var pad = 0.2;
        svg.appendChild(svgEl("rect", { class: "inset-frame", x: canBox[0] - pad, y: canBox[1] - pad,
          width: canBox[2] - canBox[0] + 2 * pad, height: canBox[3] - canBox[1] + 2 * pad }));
      }
      var m = 0.3;
      svg.setAttribute("viewBox", [minX - m, minY - m, maxX - minX + 2 * m, maxY - minY + 2 * m].join(" "));
      container.appendChild(svg);
      // Leyenda (rangos por cuantiles) + sin dato
      var legend = A.el("div", { class: "map-legend", "aria-label": "Leyenda" });
      var edges = [null].concat(breaks).concat([null]);
      colors.forEach(function (c, i) {
        var lo = edges[i], hi = edges[i + 1];
        var txt = lo === null ? "< " + A.fmt(hi) : (hi === null ? "≥ " + A.fmt(lo) : A.fmt(lo) + " – " + A.fmt(hi));
        if (!breaks.length) txt = "valor único";
        var sw = A.el("span", { class: "map-legend__swatch" });
        sw.style.background = c;
        legend.appendChild(A.el("span", { class: "map-legend__item" }, [sw, txt]));
      });
      legend.appendChild(A.el("span", { class: "map-legend__item" }, [A.el("span", { class: "map-legend__swatch map-legend__swatch--nodata" }), "Sin dato"]));
      container.appendChild(legend);
      var meta = [];
      if (opts.unit) meta.push("Unidad: " + opts.unit);
      if (opts.period) meta.push("Periodo: " + A.period(opts.period));
      meta.push("Clases por quintiles");
      container.appendChild(A.el("p", { class: "card__source", text: meta.join(" · ") }));
    }).catch(function (e) {
      A.errorState(container, "No se pudo cargar el mapa: " + e.message);
    });
  }

  window.AtalayaMap = { render: render, load: loadGeo, name: function (code) { return names[code] || code; } };
})();
