// =============================================================================
// theme.js — dark/light theme toggle + small UI niceties (RGT v3, Opus layer)
// Loaded automatically by Dash from /assets. Persists choice in localStorage.
// =============================================================================
(function () {
  "use strict";
  var KEY = "rgt-theme";
  var root = document.documentElement;

  function apply(t) {
    if (t === "dark") root.setAttribute("data-theme", "dark");
    else root.removeAttribute("data-theme");
    var btn = document.getElementById("theme-toggle");
    if (btn) {
      btn.textContent = (t === "dark") ? "☀️" : "🌙";
      btn.setAttribute("title", (t === "dark") ? "Switch to light theme" : "Switch to dark theme");
    }
  }
  function current() {
    return root.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }

  // Initial theme: saved choice → system preference → light.
  var saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) {}
  if (!saved) {
    saved = (window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches)
      ? "dark" : "light";
  }
  apply(saved);

  // Toggle (delegated, so it survives Dash re-renders).
  document.addEventListener("click", function (e) {
    var hit = e.target && (e.target.id === "theme-toggle"
      ? e.target
      : (e.target.closest && e.target.closest("#theme-toggle")));
    if (!hit) return;
    var next = current() === "dark" ? "light" : "dark";
    apply(next);
    try { localStorage.setItem(KEY, next); } catch (err) {}
  });

  // Re-assert the button glyph after Dash hydrates the layout.
  var tries = 0;
  var iv = setInterval(function () {
    apply(current());
    if (++tries > 24) clearInterval(iv);
  }, 250);

  // ---- Report film bridge: when the loading film finishes its cycle (or the
  //      report is ready and it chooses to), it posts 'rgt-reveal'. We trigger
  //      the same path as the Skip button to drop the film and show the report.
  window.addEventListener("message", function (e) {
    var d = e && e.data;
    if (d && d.type === "rgt-reveal") {
      var btn = document.getElementById("report-skip");
      if (btn) btn.click();
    }
  });
})();
