/* Asistente opcional: la respuesta del modelo se muestra como TEXTO (textContent), nunca como HTML. */
(function () {
  "use strict";
  var A = window.Atalaya;
  document.addEventListener("DOMContentLoaded", function () {
    var form = document.getElementById("chat-form");
    if (!form) return;
    var input = document.getElementById("chat-input"), log = document.getElementById("chat-log");
    var btn = form.querySelector("button[type=submit]");
    function add(text, who, note) {
      var msg = A.el("div", { class: "chat-msg chat-msg--" + who, text: text });
      if (note) msg.appendChild(A.el("span", { class: "chat-msg__note", text: note }));
      log.appendChild(msg);
      log.scrollTop = log.scrollHeight;
    }
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var q = input.value.trim();
      if (!q) { input.focus(); return; }
      add(q, "user");
      input.value = "";
      btn.disabled = true; btn.setAttribute("aria-busy", "true");
      A.fetchJSON(form.getAttribute("data-endpoint"), { method: "POST", body: { message: q }, timeout: 30000 }).then(function (r) {
        btn.disabled = false; btn.removeAttribute("aria-busy");
        if (r.ok) add(r.data.reply, "bot", r.data.disclaimer);
        else add(r.data.error || "El asistente no está disponible.", "bot");
      });
    });
  });
})();
