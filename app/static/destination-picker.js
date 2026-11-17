// Turns <select data-picker> into a search field with suggestions (combobox).
// The select stays in the form (hidden) and keeps the value, so the server side and
// the location filter (options get hidden/disabled) work unchanged.
(function () {
  "use strict";

  const fold = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

  document.querySelectorAll("select[data-picker]").forEach((select) => {
    const wrap = document.createElement("div");
    wrap.className = "picker";
    const input = document.createElement("input");
    input.type = "text";
    input.className = "picker-input";
    input.placeholder = select.dataset.placeholder || "";
    input.autocomplete = "off";
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-autocomplete", "list");
    const list = document.createElement("ul");
    list.className = "picker-list";
    list.setAttribute("role", "listbox");
    list.id = `picker-${select.name}`;
    input.setAttribute("aria-controls", list.id);
    list.hidden = true;

    select.hidden = true;
    select.removeAttribute("required");   // the visible input carries the validation
    select.after(wrap);
    wrap.append(input, list);

    let active = -1;
    let shown = [];

    const options = () => Array.from(select.options).filter((o) => o.value && !o.disabled);
    const current = () => select.selectedOptions[0];
    const showCurrent = () => {
      const opt = current();
      input.value = opt && opt.value ? opt.textContent.trim() : "";
      input.setCustomValidity(opt && opt.value ? "" : " ");
    };

    function choose(opt) {
      select.value = opt.value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
      showCurrent();
      close();
    }

    function close() {
      list.hidden = true;
      input.setAttribute("aria-expanded", "false");
      active = -1;
    }

    function highlight(i) {
      active = i;
      list.querySelectorAll("li.option").forEach((li, n) => {
        li.classList.toggle("active", n === i);
        if (n === i) li.scrollIntoView({ block: "nearest" });
      });
    }

    function render() {
      const q = fold(input.value.trim());
      const opt = current();
      // Typing the exact current name again still shows the full list
      const filtering = q && !(opt && opt.value && fold(opt.textContent.trim()) === q);
      shown = options().filter((o) => !filtering
        || fold(o.textContent).includes(q)
        || fold(o.dataset.address || "").includes(q)
        || fold(o.dataset.category || "").includes(q));
      list.textContent = "";
      let lastGroup = null;
      shown.forEach((o, i) => {
        const group = o.dataset.category || "";
        if (group !== lastGroup) {
          const head = document.createElement("li");
          head.className = "group";
          head.textContent = group;
          head.setAttribute("role", "presentation");
          list.append(head);
          lastGroup = group;
        }
        const li = document.createElement("li");
        li.className = "option";
        li.setAttribute("role", "option");
        if (o.dataset.icon) {
          const img = document.createElement("img");
          img.src = o.dataset.icon;
          img.alt = "";
          li.append(img);
        }
        const text = document.createElement("span");
        const name = document.createElement("strong");
        name.textContent = o.textContent.trim();
        const addr = document.createElement("small");
        addr.textContent = o.dataset.address || "";
        text.append(name, addr);
        li.append(text);
        li.addEventListener("mousedown", (e) => { e.preventDefault(); choose(o); });
        li.addEventListener("mousemove", () => highlight(i));
        list.append(li);
      });
      // Not found (or always at the end): create a new destination
      const location = select.form && select.form.elements.namedItem("location_id");
      const params = new URLSearchParams();
      if (input.value.trim() && filtering) params.set("name", input.value.trim());
      if (location && location.value) params.set("location_id", location.value);
      if (!shown.length) {
        const empty = document.createElement("li");
        empty.className = "empty";
        empty.textContent = select.dataset.empty || "";
        list.append(empty);
      }
      const create = document.createElement("li");
      create.className = "create";
      const a = document.createElement("a");
      a.href = "/destinations/new" + (params.toString() ? "?" + params : "");
      a.textContent = params.has("name")
        ? (select.dataset.create || "").replace("{q}", input.value.trim())
        : (select.dataset.createPlain || "");
      create.append(a);
      list.append(create);
      list.hidden = false;
      input.setAttribute("aria-expanded", "true");
      highlight(shown.length ? 0 : -1);
    }

    // A mouse press inside the list must not blur the input: blur closes the list before
    // the click arrives, so the "create new destination" link would never be followed.
    list.addEventListener("mousedown", (e) => e.preventDefault());

    input.addEventListener("focus", () => { input.select(); render(); });
    input.addEventListener("input", render);
    input.addEventListener("blur", () => { close(); showCurrent(); });
    input.addEventListener("keydown", (e) => {
      if (list.hidden && (e.key === "ArrowDown" || e.key === "ArrowUp")) { render(); return; }
      if (e.key === "ArrowDown") { e.preventDefault(); highlight(Math.min(active + 1, shown.length - 1)); }
      else if (e.key === "ArrowUp") { e.preventDefault(); highlight(Math.max(active - 1, 0)); }
      else if (e.key === "Enter") {
        if (!list.hidden && active >= 0 && shown[active]) { e.preventDefault(); choose(shown[active]); }
      } else if (e.key === "Escape") { close(); showCurrent(); }
    });
    // The location filter may deselect the destination
    select.addEventListener("change", showCurrent);
    const location = select.form && select.form.elements.namedItem("location_id");
    if (location) location.addEventListener("change", () => setTimeout(showCurrent));

    showCurrent();
  });
})();
