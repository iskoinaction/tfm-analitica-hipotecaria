/* Utilidades comunes de Atalaya. Regla: nunca innerHTML; todo el DOM se crea con nodos y textContent. */
(function () {
  "use strict";
  var NF = {};
  function nf(dec) {
    var k = String(dec);
    if (!NF[k]) NF[k] = new Intl.NumberFormat("es-ES", { minimumFractionDigits: dec, maximumFractionDigits: dec });
    return NF[k];
  }
  function autoDecimals(v) {
    var a = Math.abs(v);
    if (a >= 1000) return 0;
    if (a >= 100) return 1;
    return 2;
  }
  function fmt(v, dec, unit) {
    if (v === null || v === undefined || (typeof v === "number" && !isFinite(v))) return "—";
    if (typeof v !== "number") return String(v);
    var s = nf(dec === undefined || dec === null ? autoDecimals(v) : dec).format(v);
    return unit ? s + " " + unit : s;
  }
  function period(p) {
    var m = /^(\d{4})Q([1-4])$/.exec(String(p || ""));
    return m ? m[1] + " T" + m[2] : String(p || "");
  }
  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      var v = attrs[k];
      if (v === null || v === undefined || v === false) return;
      if (k === "text") n.textContent = v;
      else if (k === "class") n.className = v;
      else n.setAttribute(k, v === true ? "" : v);
    });
    (children || []).forEach(function (c) {
      if (c === null || c === undefined) return;
      n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return n;
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function csrf() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute("content") : "";
  }
  function fetchJSON(url, opts) {
    opts = opts || {};
    var ctrl = new AbortController();
    var timer = setTimeout(function () { ctrl.abort(); }, opts.timeout || 20000);
    var init = { method: opts.method || "GET", headers: { "Accept": "application/json" }, signal: ctrl.signal, credentials: "same-origin" };
    if (opts.body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.headers["X-CSRF-Token"] = csrf();
      init.body = JSON.stringify(opts.body);
    }
    return fetch(url, init).then(function (r) {
      clearTimeout(timer);
      return r.json().catch(function () { return {}; }).then(function (data) { return { ok: r.ok, status: r.status, data: data }; });
    }, function (err) {
      clearTimeout(timer);
      return { ok: false, status: 0, data: { error: err && err.name === "AbortError" ? "Tiempo de espera agotado." : "Error de red." } };
    });
  }
  function cssVar(name, fallback) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }
  function seriesColor(i) { return cssVar("--series-" + ((i % 8) + 1), "#2a78d6"); }
  function errorState(container, msg, retry) {
    clear(container);
    var box = el("div", { class: "error-state", role: "alert" }, [el("p", { text: msg })]);
    if (retry) {
      var b = el("button", { type: "button", class: "btn btn--secondary", text: "Reintentar" });
      b.addEventListener("click", retry);
      box.appendChild(b);
    }
    container.appendChild(box);
  }

  window.Atalaya = { fmt: fmt, period: period, el: el, clear: clear, fetchJSON: fetchJSON, cssVar: cssVar,
                     seriesColor: seriesColor, errorState: errorState, charts: [] };

  document.addEventListener("DOMContentLoaded", function () {
    // Menú lateral (drawer) en móvil
    var sidebar = document.getElementById("sidebar");
    var backdrop = document.querySelector("[data-drawer-backdrop]");
    var toggles = document.querySelectorAll("[data-drawer-toggle]");
    function setDrawer(open) {
      if (!sidebar) return;
      sidebar.setAttribute("data-open", open ? "true" : "false");
      if (backdrop) backdrop.setAttribute("data-open", open ? "true" : "false");
      toggles.forEach(function (t) { t.setAttribute("aria-expanded", open ? "true" : "false"); });
      if (open) { var first = sidebar.querySelector("a"); if (first) first.focus(); }
    }
    toggles.forEach(function (t) {
      t.addEventListener("click", function () { setDrawer(sidebar.getAttribute("data-open") !== "true"); });
    });
    if (backdrop) backdrop.addEventListener("click", function () { setDrawer(false); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && sidebar && sidebar.getAttribute("data-open") === "true") {
        setDrawer(false);
        if (toggles[0]) toggles[0].focus();
      }
    });
    // Tema claro/oscuro
    document.querySelectorAll("[data-theme-toggle]").forEach(function (b) {
      b.addEventListener("click", function () {
        var root = document.documentElement;
        var cur = root.getAttribute("data-theme");
        if (!cur) cur = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
        var next = cur === "dark" ? "light" : "dark";
        root.setAttribute("data-theme", next);
        try { localStorage.setItem("atalaya-theme", next); } catch (e) { /* sin almacenamiento */ }
        document.dispatchEvent(new CustomEvent("atalaya:theme"));
      });
    });
  });
})();
