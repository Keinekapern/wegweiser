// PDF export: form (destinations offered for the chosen locations, count) and progress.
(function () {
  "use strict";

  const form = document.getElementById("export-form");
  if (form) {
    const checked = (name) => Array.from(form.querySelectorAll(`input[name="${name}"]:checked`));
    const count = document.getElementById("export-count");

    function update() {
      const locs = checked("location_ids").map((i) => i.value);
      let n = 0;
      // a destination is offered for a location if assigned to it or to none
      form.querySelectorAll(".dest-checks label[data-locations]").forEach((label) => {
        const assigned = label.dataset.locations ? label.dataset.locations.split(",") : [];
        const offered = locs.filter((l) => !assigned.length || assigned.includes(l)).length;
        label.classList.toggle("unused", offered === 0);
        if (label.querySelector("input").checked) n += offered;
      });
      n *= checked("langs").length * checked("modes").length;
      const max = Number(count.dataset.max);
      count.textContent = n > max
        ? count.dataset.tooMany.replace("{n}", n).replace("{max}", max)
        : count.dataset.text.replace("{n}", n).replace("{min}", Math.max(1, Math.ceil(n * 2.5 / 60)));
      count.classList.toggle("warn", n > max);
    }

    form.querySelectorAll("button[data-check]").forEach((btn) => btn.addEventListener("click", () => {
      const name = btn.dataset.check === "dest" ? "destination_ids" : "langs";
      form.querySelectorAll(`input[name="${name}"]`).forEach((i) => {
        if (!i.closest("label").classList.contains("unused")) i.checked = btn.dataset.value === "1";
      });
      update();
    }));
    form.addEventListener("change", update);
    update();
  }

  const box = document.getElementById("export-status");
  if (box) {
    const labels = JSON.parse(box.dataset.labels);
    const line = box.querySelector(".status-line");
    const bar = document.getElementById("export-progress");
    const current = box.querySelector(".current");
    const problems = box.querySelector(".problems");
    const download = box.querySelector(".download");
    const error = box.querySelector(".error");

    async function poll() {
      let s;
      try {
        const r = await fetch(box.dataset.url, { cache: "no-store" });
        if (!r.ok) throw new Error(r.status);
        s = await r.json();
      } catch (e) {
        setTimeout(poll, 5000);
        return;
      }
      line.textContent = labels[s.status].replace("{done}", s.done).replace("{total}", s.total);
      bar.max = s.total; bar.value = s.done;
      current.textContent = s.status === "running" ? s.current : "";
      problems.hidden = !s.problems;
      problems.textContent = problems.dataset.text.replace("{n}", s.problems);
      if (s.status === "done") {
        download.hidden = false;
        download.querySelector(".size").textContent = (s.size / 1048576).toFixed(1).replace(".", ",") + " MB";
        bar.hidden = true;
      } else if (s.status === "failed") {
        error.hidden = false; error.textContent = s.error; bar.hidden = true;
      } else {
        setTimeout(poll, 1500);
      }
    }
    poll();
  }
})();
