// Renders start/end markers and the route on an OSM tile map.
// Tiles: tile.openstreetmap.org by default (TILE_URL), loaded on demand only (no prefetching),
// attribution visible.
(function () {
  "use strict";

  const dataEl = document.getElementById("map-data");
  const mapEl = document.getElementById("map");
  if (!dataEl || !mapEl || !window.L) return;
  const data = JSON.parse(dataEl.textContent);

  L.Icon.Default.imagePath = mapEl.ownerDocument.querySelector('script[src*="leaflet.js"]')
    .src.replace(/leaflet\.js(\?.*)?$/, "images/");

  // Print view: no fade animation, so printed tiles are never half transparent
  const isPrint = mapEl.dataset.print === "1";
  // ...and no zoom animation: a resize/refit must never be printed half-way scaled
  const mapOptions = { scrollWheelZoom: false, fadeAnimation: !isPrint, zoomAnimation: !isPrint,
                       markerZoomAnimation: !isPrint };
  const map = L.map(mapEl, mapOptions);
  window.directionsMap = map;

  const tileConf = data.tiles || {};
  const tileLayer = () => L.tileLayer(
    tileConf.url || "https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: tileConf.max_zoom || 19,
      attribution: tileConf.attribution ||
        '<a href="https://www.openstreetmap.org/copyright">&copy; OpenStreetMap</a>',
    });
  const tiles = tileLayer().addTo(map);
  // All tile layers (main map + detail maps), for the print view's "loaded" check
  window.directionsTileLayers = [tiles];

  const start = L.latLng(data.start.lat, data.start.lon);
  const end = L.latLng(data.end.lat, data.end.lon);

  // Tooltip offsets per side: around a circle of radius r, and around the default pin
  // (tooltipAnchor [16, -28] relative to the tip)
  const ringOffset = (r) => ({ top: [0, -r], bottom: [0, r], left: [-r, 0], right: [r, 0] });
  const pinOffset = { top: [-16, -14], bottom: [-16, 30], left: [-26, 14], right: [-6, 14] };
  // Main map labels, placed by layoutMain() so they don't cover each other
  const mainLabels = [];   // {layer, offsets, preferred, priority}
  const mainMarkers = [];  // [latlng, radius | null (pin)]

  // Start: circle with a permanent label (house symbol + location name)
  const startLabel = document.createElement("span");
  startLabel.className = "dest-label";
  if (data.start.icon) {
    const img = document.createElement("img");
    img.src = data.start.icon;
    img.alt = "";
    startLabel.append(img);
  }
  startLabel.append(document.createTextNode(data.start.name));
  const startMarker_ = L.circleMarker(start, { radius: 8, color: "#1d2330", weight: 3, fillColor: "#fff", fillOpacity: 1 })
    .bindTooltip(startLabel, { permanent: true, direction: "bottom", offset: [0, 8] })
    .addTo(map);
  mainLabels.push({ layer: startMarker_, offsets: ringOffset(10), preferred: "bottom", priority: 1 });
  mainMarkers.push([start, 10]);
  // Destination label with the category symbol (built via DOM, no HTML injection)
  const label = document.createElement("span");
  label.className = "dest-label";
  if (data.end.icon) {
    const img = document.createElement("img");
    img.src = data.end.icon;
    img.alt = "";
    label.append(img);
  }
  label.append(document.createTextNode(data.end.name));
  const endMarker_ = L.marker(end, { title: data.end.name })
    // The default icon's tooltipAnchor is [16, -28]; shift it to just above the pin's tip
    .bindTooltip(label, { permanent: true, direction: "top", offset: [-16, -14] })
    .addTo(map);
  mainLabels.push({ layer: endMarker_, offsets: pinOffset, preferred: "top", priority: 0 });
  mainMarkers.push([end, null]);

  const STOP_ICON = "/static/stop.svg";  // default stop sign; legs/walks carry their own (by mode)
  const makeLabel = (text, icon) => {
    const el = document.createElement("span");
    el.className = "dest-label";
    if (icon) {
      const img = document.createElement("img");
      img.src = icon;
      img.alt = "";
      el.append(img);
    }
    const name = document.createElement("span");
    name.textContent = text;
    el.append(name);
    return el;
  };
  let bounds = L.latLngBounds([start, end]);
  const mainPath = [];          // route parts as lists of latlngs (labels avoid them)
  const stopNames = new Set();
  if (data.route && data.route.legs) {
    // Public transport: walking legs dashed, rides in the line colour, stops marked
    data.route.legs.forEach((leg) => {
      if (!leg.geometry.length) return;
      const walk = leg.kind === "walk";
      const line = L.polyline(leg.geometry, walk
        ? { color: "#444", weight: 4, opacity: 0.9, dashArray: "2 8", lineCap: "round", className: "route-walk" }
        : { color: leg.color || "#1f5fbf", weight: 6, opacity: 0.9, className: "route-ride" }).addTo(map);
      bounds = bounds.extend(line.getBounds());
      mainPath.push(leg.geometry.map((c) => L.latLng(c)));
      if (!walk) {
        [[leg.geometry[0], leg.from_name], [leg.geometry[leg.geometry.length - 1], leg.to_name]]
          .forEach(([pos, name]) => {
            // a change at the same stop: one marker and label are enough
            if (stopNames.has(name)) return;
            stopNames.add(name);
            const stop = L.circleMarker(pos, { radius: 5, color: "#111", weight: 2, fillColor: "#fff", fillOpacity: 1 })
              .bindTooltip(makeLabel(name, leg.stop_icon || STOP_ICON), { permanent: true, direction: "right", className: "stop-label" })
              .addTo(map);
            mainLabels.push({ layer: stop, offsets: ringOffset(7), preferred: "right", priority: 2 });
            mainMarkers.push([L.latLng(pos), 7]);
          });
      }
    });
  } else if (data.route && data.route.geometry.length) {
    const line = L.polyline(data.route.geometry, { color: "#1f5fbf", weight: 5, opacity: 0.85, className: "route-ride" }).addTo(map);
    mainPath.push(data.route.geometry.map((c) => L.latLng(c)));
    bounds = bounds.extend(line.getBounds());
  }
  // Extra space at the top for the destination pin and its label
  const fit = () => map.fitBounds(bounds, { paddingTopLeft: [30, 70], paddingBottomRight: [30, 50],
                                            animate: false });
  fit();
  const fits = [() => { map.invalidateSize(); fit(); layoutMain(); }];

  // Attribution text in the directions language, set via DOM (no HTML injection).
  // Only possible after the map has a view: Leaflet adds layers (and their attribution) then.
  const localizeAttribution = (container) => {
    const link = container.querySelector(".leaflet-control-attribution a[href*='copyright']");
    if (link) link.textContent = data.attribution;
  };
  localizeAttribution(mapEl);

  // --- Detail maps: walk to the first stop / from the last stop ---------------

  // --- Detail map layout: zoom in as far as possible, labels never on the route ---
  const DIRS = ["top", "bottom", "right", "left"];
  const rectsOverlap = (r, q) => r.x < q.x + q.w && q.x < r.x + r.w && r.y < q.y + q.h && q.y < r.y + r.h;
  // Liang-Barsky: does the segment p-q cross rectangle r?
  const segmentHitsRect = (p, q, r) => {
    let t0 = 0, t1 = 1;
    const dx = q.x - p.x, dy = q.y - p.y;
    const checks = [[-dx, p.x - r.x], [dx, r.x + r.w - p.x], [-dy, p.y - r.y], [dy, r.y + r.h - p.y]];
    for (const [pp, qq] of checks) {
      if (pp === 0) { if (qq < 0) return false; continue; }
      const t = qq / pp;
      if (pp < 0) { if (t > t1) return false; if (t > t0) t0 = t; }
      else { if (t < t0) return false; if (t < t1) t1 = t; }
    }
    return true;
  };
  // Tooltip box in container pixels (transform position + CSS margin of the arrow class)
  const tooltipRect = (m, tooltip) => {
    const el = tooltip.getElement();
    const pos = m.layerPointToContainerPoint(L.DomUtil.getPosition(el));
    return { x: pos.x + el.offsetLeft, y: pos.y + el.offsetTop, w: el.offsetWidth, h: el.offsetHeight };
  };
  const isVertical = (dir) => dir === "top" || dir === "bottom";
  // Side of the point plus a shift along the label (e.g. "top", moved right); the
  // arrow is moved back by the same amount so it still points at the marker
  const setPlacement = (label, dir, dx, dy) => {
    const [ox, oy] = label.offsets[dir];
    label.tooltip.options.direction = dir;
    label.tooltip.options.offset = [ox + dx, oy + dy];
    label.tooltip.update();
    const el = label.tooltip.getElement();
    el.style.setProperty("--arrow-dx", `${-dx}px`);
    el.style.setProperty("--arrow-dy", `${-dy}px`);
  };
  const layoutInset = (m, { bounds, path, labels, markers, margins }) => {
    m.invalidateSize();
    const size = m.getSize();
    const room = L.point(size.x - margins.left - margins.right, size.y - margins.top - margins.bottom);
    if (room.x <= 0 || room.y <= 0) return;  // hidden (e.g. detail maps switched off)
    const pad = 4;  // distance labels keep from the route: half its width plus a little air
    const center = bounds.getCenter();
    const zMax = Math.min(19, m.getBoundsZoom(bounds, false, L.point(24, 24)));
    let best = null;  // fallback: fits, but with the fewest overlaps
    for (let z = zMax; z >= Math.max(zMax - 6, 1); z--) {
      m.setView(center, z, { animate: false });
      const pts = path.map((ll) => m.latLngToContainerPoint(ll));
      const obstacles = markers.map(([ll, r]) => {
        const c = m.latLngToContainerPoint(ll);
        return r ? { x: c.x - r, y: c.y - r, w: 2 * r, h: 2 * r }
                 : { x: c.x - 13, y: c.y - 42, w: 27, h: 43 };  // default pin icon (25x41, tip at the point)
      });
      const hits = (r) => {
        const big = { x: r.x - pad, y: r.y - pad, w: r.w + 2 * pad, h: r.h + 2 * pad };
        return obstacles.filter((o) => rectsOverlap(r, o)).length
          + pts.filter((p, i) => i > 0 && segmentHitsRect(pts[i - 1], p, big)).length;
      };
      // All candidate placements per label: measure each side once, shifts are arithmetic
      const cands = labels.map((label) => {
        const list = [];
        DIRS.forEach((dir) => {
          setPlacement(label, dir, 0, 0);
          const r = tooltipRect(m, label.tooltip);
          const s = isVertical(dir) ? Math.max(0, r.w / 2 - 14) : Math.max(0, r.h / 2 - 8);
          [0, s, -s].forEach((shift, k) => {
            const [dx, dy] = isVertical(dir) ? [shift, 0] : [0, shift];
            const rect = { x: r.x + dx, y: r.y + dy, w: r.w, h: r.h };
            list.push({ dir, dx, dy, rect, hits: hits(rect),
                        rank: (dir === label.preferred ? 0 : 1) + (k ? 2 : 0) });
          });
        });
        return list;
      });
      let found = null;
      cands[0].forEach((c0) => cands[1].forEach((c1) => {
        const conflicts = c0.hits + c1.hits + (rectsOverlap(c0.rect, c1.rect) ? 1 : 0);
        // Everything (route, markers, labels) must fit into the map
        const all = [c0.rect, c1.rect, ...obstacles, ...pts.map((p) => ({ x: p.x, y: p.y, w: 0, h: 0 }))];
        const x0 = Math.min(...all.map((r) => r.x)), y0 = Math.min(...all.map((r) => r.y));
        const x1 = Math.max(...all.map((r) => r.x + r.w)), y1 = Math.max(...all.map((r) => r.y + r.h));
        if (x1 - x0 > room.x || y1 - y0 > room.y) return;
        const option = { z, combo: [c0, c1], conflicts, rank: c0.rank + c1.rank,
                         shift: L.point((x0 + x1) / 2 - (margins.left + room.x / 2),
                                        (y0 + y1) / 2 - (margins.top + room.y / 2)) };
        if (!conflicts && (!found || option.rank < found.rank)) found = option;
        if (!best || conflicts < best.conflicts) best = option;
      }));
      if (found) { best = found; break; }
    }
    if (!best) {  // not even the route fits: preferred sides, plain fit
      labels.forEach((l) => setPlacement(l, l.preferred, 0, 0));
      m.fitBounds(bounds, { padding: [24, 24], maxZoom: 19, animate: false });
      return;
    }
    if (m.getZoom() !== best.z) m.setView(center, best.z, { animate: false });
    best.combo.forEach((c, i) => setPlacement(labels[i], c.dir, c.dx, c.dy));
    m.panBy(best.shift.round(), { animate: false });
  };

  // --- Main map: each label on the side where it covers the least ---------------
  // Every label gets candidate positions (4 sides, also shifted along the side). A
  // candidate costs what it covers: another label > the destination pin > a circle >
  // the route. First the labels are placed one by one (destination, start, stops),
  // then each may move again now that all others stand.
  const layoutMain = () => {
    if (!mainLabels.length || !map.getSize().x) return;
    const pad = 2;
    const pts = mainPath.map((part) => part.map((ll) => map.latLngToContainerPoint(ll)));
    const obstacles = mainMarkers.map(([ll, r]) => {
      const c = map.latLngToContainerPoint(ll);
      return r ? { x: c.x - r, y: c.y - r, w: 2 * r, h: 2 * r, cost: 10 }
               : { x: c.x - 13, y: c.y - 42, w: 27, h: 43, cost: 40 };   // pin
    });
    const entries = [...mainLabels].sort((a, b) => a.priority - b.priority).map((entry) => {
      const label = { tooltip: entry.layer.getTooltip(), offsets: entry.offsets };
      const cands = [];
      DIRS.forEach((dir) => {
        setPlacement(label, dir, 0, 0);
        const r = tooltipRect(map, label.tooltip);
        const s = isVertical(dir) ? Math.max(0, r.w / 2 - 14) : Math.max(0, r.h / 2 - 8);
        [0, s, -s].forEach((shift, k) => {
          const [dx, dy] = isVertical(dir) ? [shift, 0] : [0, shift];
          const rect = { x: r.x + dx, y: r.y + dy, w: r.w, h: r.h };
          const fixed = obstacles.reduce((n, o) => n + (rectsOverlap(rect, o) ? o.cost : 0), 0)
            + Math.min(9, pts.reduce((n, part) => n + part.filter(
                (p, i) => i > 0 && segmentHitsRect(part[i - 1], p, rect)).length, 0));
          cands.push({ dir, dx, dy, rect, fixed,
                       rank: (dir === entry.preferred ? 0 : 1) + (k ? 2 : 0) });
        });
      });
      return { label, cands, chosen: null };
    });
    const grow = (r) => ({ x: r.x - pad, y: r.y - pad, w: r.w + 2 * pad, h: r.h + 2 * pad });
    const cost = (cand, self) => cand.fixed + 100 * entries.filter(
      (e) => e !== self && e.chosen && rectsOverlap(grow(cand.rect), e.chosen.rect)).length;
    const pick = (entry) => {
      entry.chosen = entry.cands.reduce((best, c) => {
        const v = cost(c, entry), w = cost(best, entry);
        return v < w || (v === w && c.rank < best.rank) ? c : best;
      });
    };
    entries.forEach(pick);
    for (let pass = 0; pass < 2; pass++) entries.forEach(pick);
    entries.forEach((e) => setPlacement(e.label, e.chosen.dir, e.chosen.dx, e.chosen.dy));
  };
  layoutMain();
  // zooming in the print view moves markers relative to their labels
  map.on("zoomend", layoutMain);

  (data.walk_details || []).forEach((walk, i) => {
    const el = document.querySelector(`.inset-map[data-inset="${i}"]`);
    if (!el || !walk.geometry.length) return;
    const inset = L.map(el, { ...mapOptions, zoomControl: !isPrint, attributionControl: true });
    const layer = tileLayer().addTo(inset);
    window.directionsTileLayers.push(layer);
    inset.attributionControl.setPrefix(false);
    const path = L.polyline(walk.geometry, { color: "#1f5fbf", weight: 5, opacity: 0.9,
                                             dashArray: "2 9", lineCap: "round", className: "route-walk" })
      .addTo(inset);
    const a = L.latLng(walk.start.lat, walk.start.lon);
    const b = L.latLng(walk.end.lat, walk.end.lon);
    const stopMarker = { radius: 6, color: "#111", weight: 2, fillColor: "#fff", fillOpacity: 1 };
    const startMarker = { radius: 7, color: "#1d2330", weight: 3, fillColor: "#fff", fillOpacity: 1 };
    // Put each label on the side facing away from the other point, so they never overlap
    const away = (p, q) => {
      const dy = p.lat - q.lat;
      const dx = (p.lng - q.lng) * Math.cos(p.lat * Math.PI / 180);
      if (Math.abs(dy) >= Math.abs(dx)) return dy >= 0 ? "top" : "bottom";
      return dx >= 0 ? "right" : "left";
    };
    const circleOffset = ringOffset(8);
    const dirA = away(a, b);
    const dirB = away(b, a);
    // labels: [tooltip, point, offsets per direction, preferred direction]
    let labelA, labelB;
    if (walk.kind === "to_stop") {
      labelA = L.circleMarker(a, startMarker)
        .bindTooltip(makeLabel(walk.start.name, data.start.icon),
                     { permanent: true, direction: dirA, offset: circleOffset[dirA] })
        .addTo(inset);
      labelB = L.circleMarker(b, stopMarker)
        .bindTooltip(makeLabel(walk.end.name, walk.stop_icon || STOP_ICON),
                     { permanent: true, direction: dirB, offset: circleOffset[dirB], className: "stop-label" })
        .addTo(inset);
    } else {
      labelA = L.circleMarker(a, stopMarker)
        .bindTooltip(makeLabel(walk.start.name, walk.stop_icon || STOP_ICON),
                     { permanent: true, direction: dirA, offset: circleOffset[dirA], className: "stop-label" })
        .addTo(inset);
      labelB = L.marker(b, { title: walk.end.name })
        .bindTooltip(makeLabel(walk.end.name, data.end.icon),
                     { permanent: true, direction: dirB, offset: pinOffset[dirB] })
        .addTo(inset);
    }
    const labels = [
      { tooltip: labelA.getTooltip(), offsets: circleOffset, preferred: dirA },
      { tooltip: labelB.getTooltip(), offsets: walk.kind === "to_stop" ? circleOffset : pinOffset, preferred: dirB },
    ];
    const insetBounds = path.getBounds().extend(a).extend(b);
    const fitInset = () => layoutInset(inset, {
      bounds: insetBounds, path: walk.geometry.map((c) => L.latLng(c)), labels,
      // obstacles in pixels around a point: circles, and the destination pin above its tip
      markers: [[a, 9], [b, walk.kind === "to_stop" ? 8 : null]],
      margins: { top: 8, right: 8, bottom: 18, left: isPrint ? 8 : 44 },
    });
    fitInset();
    localizeAttribution(el);
    fits.push(() => { inset.invalidateSize(); fitInset(); });
  });

  // Used by the print view after map containers were resized
  window.directionsFit = () => fits.forEach((f) => f());
})();
