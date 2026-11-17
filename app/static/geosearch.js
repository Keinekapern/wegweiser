// OSM search panel: queries the backend (/api/geocode), which throttles and caches
// requests to Nominatim. Search runs only on explicit submit (no autocomplete,
// per Nominatim usage policy).
(function () {
  "use strict";

  const I18N = JSON.parse((document.getElementById("i18n") || {}).textContent || "{}");
  function t(msgid, params) {
    let text = I18N[msgid] || msgid;
    Object.entries(params || {}).forEach(([k, v]) => { text = text.split(`{${k}}`).join(String(v)); });
    return text;
  }

  const FIELDS = ["name", "address", "lat", "lon", "phone", "website", "opening_hours", "osm_type", "osm_id"];

  function el(tag, attrs, text) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => node.setAttribute(k, v));
    if (text) node.textContent = text;
    return node;
  }

  function fillForm(form, result) {
    FIELDS.forEach((field) => {
      const input = form.elements.namedItem(field);
      if (!input) return;
      const value = result[field];
      // Don't wipe values the user already entered with empty OSM data
      // (except the OSM reference, which must match the chosen result).
      if (value === null || value === undefined || value === "") {
        if (field === "osm_type" || field === "osm_id") input.value = "";
        return;
      }
      input.value = String(value);
    });
    // Category proposed from the OSM tags (only if the form has the field and nothing is chosen)
    const coords = form.elements.namedItem("coords");
    if (coords && result.lat != null && result.lon != null) {
      coords.value = `${Number(result.lat).toFixed(6)}, ${Number(result.lon).toFixed(6)}`;
    }
    const phone = form.elements.namedItem("phone");
    if (phone) phone.dispatchEvent(new Event("change"));   // normalize prefilled number
    const cat = form.elements.namedItem("category");
    if (cat && result.dest_category && !cat.value) cat.value = result.dest_category;
    // Translated names from OSM (name:en, name:ar, ...): only into empty fields
    let anyName = false;
    Object.entries(result.names || {}).forEach(([lang, value]) => {
      const input = form.querySelector(`input[name="name_${lang}"]`);
      if (input && !input.value) { input.value = value; anyName = true; }
    });
    const details = form.querySelector("details.name-translations");
    if (details && anyName) details.open = true;
    const ref = form.querySelector(".osm-ref");
    if (ref) {
      ref.textContent = "";
      if (result.osm_type && result.osm_id) {
        ref.append(t("OSM-Objekt") + ": ");
        ref.append(el("a", {
          href: `https://www.openstreetmap.org/${result.osm_type}/${result.osm_id}`,
          target: "_blank", rel: "noopener",
        }, `${result.osm_type}/${result.osm_id}`));
      }
    }
    const notice = form.querySelector(".geosearch-filled");
    if (notice) notice.hidden = false;
    const nameInput = form.elements.namedItem("name");
    if (nameInput) nameInput.focus();
  }

  function renderResult(result, onPick) {
    const li = el("li");
    const pick = el("button", { type: "button", class: "geosearch-pick" });
    pick.append(el("strong", {}, result.name));
    pick.append(el("span", { class: "small" }, result.address || result.display_name));
    const extras = [result.type, result.phone, result.opening_hours].filter(Boolean).join(" · ");
    if (extras) pick.append(el("span", { class: "small hint" }, extras));
    pick.addEventListener("click", () => onPick(result));
    li.append(pick);
    if (result.osm_type && result.osm_id) {
      li.append(el("a", {
        href: `https://www.openstreetmap.org/${result.osm_type}/${result.osm_id}`,
        target: "_blank", rel: "noopener", class: "small",
      }, t("auf Karte prüfen")));
    }
    return li;
  }

  document.querySelectorAll("[data-geosearch]").forEach((panel) => {
    const searchForm = panel.querySelector(".geosearch-form");
    const status = panel.querySelector(".geosearch-status");
    const list = panel.querySelector(".geosearch-results");
    const attribution = panel.querySelector(".geosearch-attribution");
    const button = searchForm.querySelector("button");
    const target = document.getElementById(panel.dataset.target);

    // "Create new destination" from the picker: search right away (user-triggered)
    if (panel.hasAttribute("data-autosearch") && searchForm.elements.q.value.trim().length >= 3) {
      setTimeout(() => searchForm.requestSubmit());
    }

    searchForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const q = searchForm.elements.q.value.trim();
      if (q.length < 3) {
        status.textContent = t("Bitte mindestens 3 Zeichen eingeben.");
        return;
      }
      button.disabled = true;
      status.textContent = t("Suche läuft …");
      list.textContent = "";
      try {
        const resp = await fetch(`/api/geocode?q=${encodeURIComponent(q)}`);
        const data = await resp.json();
        if (!resp.ok) {
          status.textContent = data.error || t("Die Suche ist fehlgeschlagen.");
          return;
        }
        attribution.textContent = data.attribution;
        attribution.hidden = false;
        if (!data.results.length) {
          status.textContent = t("Keine Treffer. Andere Schreibweise oder Adresse versuchen.");
          return;
        }
        status.textContent = t("{n} Treffer – zum Übernehmen anklicken:", { n: data.results.length });
        data.results.forEach((r) => list.append(renderResult(r, (picked) => {
          fillForm(target, picked);
          list.textContent = "";
          status.textContent = t("„{name}“ übernommen.", { name: picked.name });
        })));
      } catch (err) {
        status.textContent = t("Die Suche ist fehlgeschlagen (keine Verbindung zum Server).");
      } finally {
        button.disabled = false;
      }
    });
  });
})();
