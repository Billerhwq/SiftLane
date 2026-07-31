(function () {
  "use strict";

  var M = window.DS_MANIFEST;
  if (!M || !Array.isArray(M.variants) || M.variants.length === 0) {
    document.body.innerHTML =
      '<pre style="padding:24px;font:14px monospace;color:#900">' +
      "DS_MANIFEST missing or empty. Expected sibling manifest.js with " +
      "window.DS_MANIFEST = { title, subtitle, variants: [{ id, label, file }] }." +
      "</pre>";
    return;
  }

  var SK_PREFIX = "ds_scroll_";
  var VK = "ds_variant_" + (M.id || location.pathname);

  var titleEl = document.querySelector(".board-title");
  var subEl = document.getElementById("boardSub");
  var tabsEl = document.getElementById("boardTabs");
  var frameEl = document.getElementById("variantFrame");

  if (titleEl && M.title) titleEl.textContent = M.title;
  if (subEl && M.subtitle) subEl.textContent = M.subtitle;
  if (M.title) document.title = M.title;

  M.variants.forEach(function (v) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "board-tab";
    b.dataset.id = v.id;
    b.textContent = v.label || v.id;
    tabsEl.appendChild(b);
  });

  function variantById(id) {
    for (var i = 0; i < M.variants.length; i++) {
      if (M.variants[i].id === id) return M.variants[i];
    }
    return null;
  }

  var stored = sessionStorage.getItem(VK);
  var current = variantById(stored) ? stored : M.variants[0].id;

  function saveScroll() {
    try {
      var w = frameEl.contentWindow;
      if (w && w.document) {
        var y = w.scrollY || w.document.documentElement.scrollTop || 0;
        sessionStorage.setItem(SK_PREFIX + current, String(y));
      }
    } catch (_) {
      // cross-origin or not loaded yet
    }
  }

  function restoreScroll() {
    try {
      var y = parseInt(sessionStorage.getItem(SK_PREFIX + current) || "0", 10);
      var w = frameEl.contentWindow;
      if (w) w.scrollTo(0, isNaN(y) ? 0 : y);
    } catch (_) {}
  }

  function attachIframeScroll() {
    try {
      var w = frameEl.contentWindow;
      if (!w) return;
      w.addEventListener("scroll", saveScroll, { passive: true });
      w.addEventListener("beforeunload", saveScroll);
    } catch (_) {}
  }

  function activate(id, isInitial) {
    if (!isInitial) saveScroll();
    current = id;
    sessionStorage.setItem(VK, id);
    var btns = tabsEl.querySelectorAll(".board-tab");
    for (var i = 0; i < btns.length; i++) {
      btns[i].classList.toggle("active", btns[i].dataset.id === id);
    }
    var v = variantById(id);
    if (!v) return;
    frameEl.src = v.file;
  }

  frameEl.addEventListener("load", function () {
    restoreScroll();
    attachIframeScroll();
  });

  tabsEl.addEventListener("click", function (e) {
    var t = e.target.closest("[data-id]");
    if (!t) return;
    if (t.dataset.id === current) return;
    activate(t.dataset.id, false);
  });

  window.addEventListener("beforeunload", saveScroll);

  activate(current, true);
})();
