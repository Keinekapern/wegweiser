// Print view: enable printing only once all map tiles are loaded.
(function () {
  "use strict";

  const button = document.getElementById("print-button");
  const status = document.getElementById("map-status");
  const strings = JSON.parse(document.getElementById("i18n-print").textContent);
  // Tile layers of the main map and the detail maps (see directions-map.js)
  const layers = window.directionsTileLayers || [];
  let loaded = false;
  const errors = new Map(layers.map((l) => [l, 0]));

  function update() {
    if (!layers.length) {          // map script failed: never claim "ready"
      status.textContent = strings.tile_errors.replace("{n}", "?");
      status.classList.add("warn");
      return;
    }
    if (layers.some((l) => l.isLoading())) {
      loaded = false;
      status.classList.remove("ok", "warn");
      return;
    }
    button.disabled = false;
    // Leaflet also counts failed tiles as "loaded" -> report them instead of "ready"
    const failed = Array.from(errors.values()).reduce((a, b) => a + b, 0);
    loaded = failed === 0;
    status.textContent = loaded ? strings.ready : strings.tile_errors.replace("{n}", failed);
    status.classList.toggle("ok", loaded);
    status.classList.toggle("warn", !loaded);
  }

  layers.forEach((layer) => {
    // "load" fires whenever all visible tiles of a layer have loaded (also after pan/zoom)
    layer.on("load", update);
    layer.on("tileerror", () => errors.set(layer, errors.get(layer) + 1));
    layer.on("loading", () => { errors.set(layer, 0); update(); });
  });
  update();
  // Never block printing completely (e.g. tile server unreachable)
  setTimeout(() => { button.disabled = false; }, 15000);

  button.addEventListener("click", () => {
    if (!loaded && !window.confirm(strings.confirm)) return;
    window.print();
  });

  // Black-and-white printing; the choice is remembered per browser (optional)
  const bw = document.getElementById("toggle-bw");
  if (bw) {
    const fromUrl = new URLSearchParams(window.location.search).get("bw");
    if (fromUrl !== null) {
      bw.checked = fromUrl === "1";
    } else {
      try { bw.checked = window.localStorage.getItem("print-bw") === "1"; } catch (e) { /* ignore */ }
    }
    const syncBw = () => {
      document.body.classList.toggle("bw", bw.checked);
      try { window.localStorage.setItem("print-bw", bw.checked ? "1" : "0"); } catch (e) { /* ignore */ }
    };
    syncBw();
    bw.addEventListener("change", syncBw);
  }

  // --- Layout: orientation, map fills the free space, details to page 2 if needed ---
  const MM = 96 / 25.4;              // CSS px per mm
  const page1 = document.getElementById("page1");
  // Below this height (portrait), steps/transit details move to page 2
  const MIN_MAP_PORTRAIT = Number(page1.dataset.minMap || 100) * MM;
  const details = document.getElementById("details");
  const sheet2 = document.getElementById("sheet2");
  const mapEl = document.getElementById("map");
  const pageStyle = document.getElementById("page-style");
  const orientation = document.getElementById("orientation");

  function hasVisibleContent(el) {
    return Array.from(el.children).some((c) => c.offsetParent !== null || c.getClientRects().length);
  }

  // Turn-by-turn texts of the walks (public transport): first candidates for page 2
  const walkSteps = Array.from(details.querySelectorAll(".walk-steps"));
  const isVisible = (el) => el.offsetParent !== null || el.getClientRects().length > 0;

  function squeezed(landscape) {
    if (!hasVisibleContent(details) || details.parentElement !== page1) return false;
    return landscape
      ? details.scrollHeight > details.clientHeight + 1   // side column overflows
      : mapEl.clientHeight < MIN_MAP_PORTRAIT;            // map too small
  }

  function layout() {
    const landscape = orientation.value === "landscape";
    document.body.classList.toggle("landscape", landscape);
    pageStyle.textContent = `@page { size: A4 ${landscape ? "landscape" : "portrait"}; margin: 12mm; }`;

    // Start with everything on page 1, then measure
    page1.append(details);
    walkSteps.forEach((el) => details.append(el));
    page1.classList.remove("details-moved", "compact");
    sheet2.hidden = true;

    if (squeezed(landscape)) {
      // Stage 1: only the walking turn-by-turn texts go to page 2
      const moved = walkSteps.filter(isVisible);
      moved.forEach((el) => sheet2.append(el));
      if (moved.length) sheet2.hidden = false;
      // Stage 2: set the details a little tighter
      if (squeezed(landscape)) page1.classList.add("compact");
      // Stage 3: still too tight -> all details to page 2 (before the walking texts), full size
      if (squeezed(landscape)) {
        page1.classList.remove("compact");
        sheet2.prepend(details);
        page1.classList.add("details-moved");
        sheet2.hidden = false;
      }
    }
    if (window.directionsFit) window.directionsFit();
  }

  // Orientation: URL (?orientation=landscape) > remembered choice > portrait
  const fromUrlOrientation = new URLSearchParams(window.location.search).get("orientation");
  let stored = null;
  try { stored = window.localStorage.getItem("print-orientation"); } catch (e) { /* ignore */ }
  orientation.value = fromUrlOrientation || stored || "portrait";
  if (!["portrait", "landscape"].includes(orientation.value)) orientation.value = "portrait";
  orientation.addEventListener("change", () => {
    try { window.localStorage.setItem("print-orientation", orientation.value); } catch (e) { /* ignore */ }
    layout();
  });

  const insets = document.getElementById("toggle-insets");
  if (insets) {
    const syncInsets = () => document.body.classList.toggle("no-insets", !insets.checked);
    syncInsets();
    insets.addEventListener("change", () => { syncInsets(); layout(); });
  }

  const toggle = document.getElementById("toggle-steps");
  if (toggle) {
    // ?steps=1 in the URL turns the texts on (e.g. for links); browsers may also
    // restore the checkbox state on reload: sync once, then on change
    if (new URLSearchParams(window.location.search).get("steps") === "1") toggle.checked = true;
    const sync = () => document.body.classList.toggle("with-steps", toggle.checked);
    sync();
    toggle.addEventListener("change", () => { sync(); layout(); });
  }

  layout();
  // Fonts and images (QR codes, symbols) can change heights after the first layout
  window.addEventListener("load", layout);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(layout);
})();
