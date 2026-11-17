// Destination form helpers: phone number in international format, Google Maps search.
(function () {
  "use strict";
  const form = document.getElementById("destination-form");
  if (!form) return;

  // Same rules as app/validation.py normalize_phone (the server normalizes again on save)
  function normalizePhone(raw, cc = "49") {
    let t = raw.trim();
    if (!t) return "";
    t = t.replace(/\//g, " ").replace(/\(0\)/g, " ").replace(/[()]/g, " ").replace(/\s+/g, " ").trim();
    if (t.startsWith("00")) t = "+" + t.slice(2).trimStart();
    else if (t.startsWith("0")) t = `+${cc} ` + t.slice(1).trimStart();
    else if (!t.startsWith("+")) return t;
    if (t.startsWith(`+${cc}`) && !t.startsWith(`+${cc} `)) t = `+${cc} ` + t.slice(cc.length + 1).trimStart();
    return t.replace(/\s+/g, " ").trim();
  }

  const phone = form.elements.namedItem("phone");
  if (phone) phone.addEventListener("change", () => { phone.value = normalizePhone(phone.value); });

  // Open a Google Maps search for name + address, to find and copy the verified place link
  const search = document.getElementById("google-search");
  if (search) {
    search.addEventListener("click", () => {
      const name = form.elements.namedItem("name").value.trim();
      const address = form.elements.namedItem("address").value.trim();
      const query = [name, address].filter(Boolean).join(", ");
      const url = "https://www.google.com/maps/search/?api=1&query=" + encodeURIComponent(query);
      window.open(url, "_blank", "noopener");
    });
  }
  const open = document.getElementById("google-open");
  const link = form.elements.namedItem("google_maps_url");
  if (open && link) {
    const sync = () => { open.disabled = !/^https:\/\//.test(link.value.trim()); };
    sync();
    link.addEventListener("input", sync);
    open.addEventListener("click", () => window.open(link.value.trim(), "_blank", "noopener"));
  }
})();
