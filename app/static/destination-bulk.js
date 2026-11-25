// Bulk entry of destinations: every line is searched one after another via the backend
// (/api/geocode, which throttles and caches Nominatim to 1 request/s). The chosen hits
// are sent as JSON items to POST /destinations/bulk.
(function () {
  "use strict";

  const I18N = JSON.parse((document.getElementById("i18n") || {}).textContent || "{}");
  function t(msgid, params) {
    let text = I18N[msgid] || msgid;
    Object.entries(params || {}).forEach(([k, v]) => { text = text.split(`{${k}}`).join(String(v)); });
    return text;
  }
  function el(tag, attrs, text) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => node.setAttribute(k, v));
    if (text) node.textContent = text;
    return node;
  }

  const searchForm = document.getElementById("bulk-search");
  const saveForm = document.getElementById("bulk-save");
  if (!searchForm || !saveForm) return;
  const DATA = JSON.parse(document.getElementById("bulk-data").textContent);
  const status = document.querySelector(".bulk-status");
  const tbody = saveForm.querySelector("tbody");
  const attribution = saveForm.querySelector(".bulk-attribution");
  const categoryTemplate = document.getElementById("bulk-category");
  const rows = [];   // {check, name, category, select, results}

  const osmRef = (r) => (r.osm_type && r.osm_id ? `${r.osm_type}/${r.osm_id}` : "");

  function makeRow(query, results) {
    const tr = el("tr");
    const row = { results };
    rows.push(row);

    const tdCheck = el("td");
    row.check = el("input", { type: "checkbox", "aria-label": t("Anlegen") });
    tdCheck.append(row.check);

    const tdHit = el("td");
    tdHit.append(el("div", { class: "small hint" }, query));
    const note = el("div", { class: "small" });
    row.name = el("input", { "aria-label": t("Name") });
    row.category = categoryTemplate.content.firstElementChild.cloneNode(true);
    row.category.setAttribute("aria-label", t("Kategorie"));

    if (!results.length) {
      row.check.disabled = true;
      row.name.disabled = true;
      row.category.disabled = true;
      note.append(t("Keine Treffer.") + " ");
      note.append(el("a", { href: `/destinations/new?name=${encodeURIComponent(query)}`, target: "_blank",
                            rel: "noopener" }, t("einzeln anlegen")));
      tdHit.append(note);
    } else {
      row.select = el("select", { "aria-label": t("Treffer") });
      results.forEach((r, i) => {
        const label = [r.name, r.address || r.display_name].filter(Boolean).join(" – ");
        row.select.append(el("option", { value: String(i) }, label));
      });
      const link = el("a", { target: "_blank", rel: "noopener", class: "small" }, t("auf Karte prüfen"));
      const apply = () => {
        const r = results[Number(row.select.value)];
        row.name.value = r.name || "";
        row.category.value = r.dest_category || "";
        if (row.category.value !== (r.dest_category || "")) row.category.value = "";
        const ref = osmRef(r);
        link.hidden = !ref;
        if (ref) link.href = `https://www.openstreetmap.org/${ref}`;
        note.textContent = "";
        const known = DATA.existing[ref];
        const twice = ref && rows.some((o) => o !== row && o.select && o.check.checked
                                            && osmRef(o.results[Number(o.select.value)]) === ref);
        if (known) note.append(t("Schon in der Zielliste: „{name}“", { name: known }));
        else if (twice) note.append(t("Doppelt in dieser Liste"));
        else if (!r.address) note.append(t("Ohne Adresse – bitte einzeln anlegen."));
        row.check.checked = !known && !twice && Boolean(r.address);
      };
      row.select.addEventListener("change", apply);
      tdHit.append(row.select, " ", link, note);
      apply();
    }
    tr.append(tdCheck, tdHit, el("td"), el("td"));
    tr.children[2].append(row.name);
    tr.children[3].append(row.category);
    tbody.append(tr);
  }

  searchForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const seen = new Set();
    const lines = searchForm.elements.lines.value.split("\n").map((l) => l.trim())
      .filter((l) => l && !seen.has(l.toLowerCase()) && seen.add(l.toLowerCase()));
    if (lines.length > DATA.max) {
      status.textContent = t("Bitte höchstens {n} Zeilen eingeben.", { n: DATA.max });
      return;
    }
    if (lines.some((l) => l.length < 3)) {
      status.textContent = t("Bitte mindestens 3 Zeichen eingeben.");
      return;
    }
    const button = searchForm.querySelector("button");
    button.disabled = true;
    rows.length = 0;
    tbody.textContent = "";
    saveForm.hidden = false;
    try {
      for (let i = 0; i < lines.length; i++) {
        status.textContent = t("Suche {i} von {n} …", { i: i + 1, n: lines.length });
        let resp, data;
        try {
          resp = await fetch(`/api/geocode?q=${encodeURIComponent(lines[i].slice(0, 200))}`);
          data = await resp.json();
        } catch (err) {
          status.textContent = t("Die Suche ist fehlgeschlagen (keine Verbindung zum Server).");
          return;
        }
        if (!resp.ok) {   // e.g. Nominatim refused: stop instead of hammering it
          status.textContent = data.error || t("Die Suche ist fehlgeschlagen.");
          return;
        }
        attribution.textContent = data.attribution;
        makeRow(lines[i], data.results);
      }
      const found = rows.filter((r) => r.results.length).length;
      status.textContent = t("{found} von {n} Zeilen gefunden. Treffer prüfen, dann „Ausgewählte anlegen“.",
                             { found, n: lines.length });
    } finally {
      button.disabled = false;
    }
  });

  saveForm.addEventListener("submit", (event) => {
    saveForm.querySelectorAll("input[name=item]").forEach((n) => n.remove());
    let count = 0;
    rows.forEach((row) => {
      if (!row.select || !row.check.checked) return;
      const r = row.results[Number(row.select.value)];
      const item = { ...r, name: row.name.value.trim(), category: row.category.value };
      saveForm.append(el("input", { type: "hidden", name: "item", value: JSON.stringify(item) }));
      count++;
    });
    if (!count) {
      event.preventDefault();
      status.textContent = t("Keine Zeile ausgewählt.");
    }
  });
})();
