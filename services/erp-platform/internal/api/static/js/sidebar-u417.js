/* Lucian UX/UI Prompt #417 · MIT License (c) 2026 Seokwoooo · https://lucianlabs.dev/uxui-prompt/#417 */
(() => {
  const root = document.querySelector(".u417");
  if (!root) return;

  const pl = root.querySelector(".u417-pl");
  const tg = root.querySelector(".u417-tg");
  const sb = root.querySelector(".u417-sb");
  const badge = document.getElementById("u417IncidentBadge");
  const its = Array.prototype.slice.call(root.querySelectorAll(".u417-it"));
  if (!pl || !tg || !sb || !its.length) return;

  const STORAGE_KEY = "axs_sidebar_rail";
  let act = its.find((it) => it.getAttribute("aria-current") === "page" || it.classList.contains("active")) || its[0];
  let rail = false;

  sb.id = "u417-erp-sb";
  tg.setAttribute("aria-controls", sb.id);

  function slide(instant = false) {
    if (!act || !act.parentNode) return;
    if (instant) {
      pl.style.transition = "none";
    }
    pl.style.setProperty("--py", `${act.parentNode.offsetTop}px`);
    if (instant) {
      void pl.offsetWidth;
      pl.style.transition = "";
    }
  }

  function applyRail(nextRail, persist = true) {
    rail = Boolean(nextRail);
    root.classList.toggle("is-rail", rail);
    tg.setAttribute("aria-expanded", String(!rail));
    tg.setAttribute("aria-label", rail ? "Expand sidebar" : "Collapse sidebar");
    if (persist) {
      try {
        localStorage.setItem(STORAGE_KEY, rail ? "1" : "0");
      } catch (_) {}
    }
    slide(false);
  }

  its.forEach((a, i) => {
    const labelEl = a.querySelector(".u417-lb");
    if (labelEl && !a.getAttribute("title")) {
      a.setAttribute("title", labelEl.textContent.trim());
    }
    a.addEventListener("click", () => {
      its.forEach((el) => el.removeAttribute("aria-current"));
      act = a;
      a.setAttribute("aria-current", "page");
      slide(false);
    });
    a.addEventListener("keydown", (e) => {
      let to = null;
      if (e.key === "ArrowDown") to = i + 1;
      else if (e.key === "ArrowUp") to = i - 1;
      else if (e.key === "Home") to = 0;
      else if (e.key === "End") to = its.length - 1;
      if (to === null || !its[to]) return;
      e.preventDefault();
      its[to].focus();
    });
  });

  tg.addEventListener("click", () => {
    applyRail(!rail, true);
  });

  sb.addEventListener("transitionend", (e) => {
    if (e.target === sb && e.propertyName === "width") {
      window.dispatchEvent(new Event("resize"));
    }
  });

  let stored = null;
  try {
    stored = localStorage.getItem(STORAGE_KEY);
  } catch (_) {}
  const initialRail = stored !== null ? stored === "1" : window.innerWidth < 900;
  applyRail(initialRail, false);
  slide(true);

  window.U417Sidebar = {
    setActive(tabName) {
      const target = its.find((it) => it.dataset.tab === tabName);
      if (!target) return;
      its.forEach((el) => el.removeAttribute("aria-current"));
      act = target;
      target.setAttribute("aria-current", "page");
      slide(false);
    },
    setIncidentCount(count) {
      if (!badge) return;
      const n = Number(count) || 0;
      if (n > 0) {
        badge.textContent = n > 99 ? "99+" : String(n);
        badge.hidden = false;
      } else {
        badge.hidden = true;
      }
    },
    slide,
  };
})();
