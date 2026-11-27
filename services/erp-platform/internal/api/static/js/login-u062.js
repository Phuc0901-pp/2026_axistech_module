/* Lucian UX/UI Prompt #062 · MIT License (c) 2026 Seokwoooo · https://lucianlabs.dev/uxui-prompt/#062 */
(() => {
  const savedTheme = localStorage.getItem("axs_theme") || "dark";
  document.documentElement.dataset.theme = savedTheme;

  const themeBtn = document.getElementById("loginThemeBtn");
  if (themeBtn) {
    themeBtn.addEventListener("click", () => {
      const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      localStorage.setItem("axs_theme", next);
    });
  }

  const root = document.querySelector(".u062");
  if (!root) return;

  const form = root.querySelector(".u062-login");
  const hi = root.querySelector(".u062-hi");
  const emailF = root.querySelector(".u062-em");
  const emailInput = emailF.querySelector("input");
  const pwF = root.querySelector(".u062-pw");
  const pw = pwF.querySelector("input");
  const err = pwF.querySelector(".u062-err span");
  const eye = root.querySelector(".u062-eye");
  const caps = root.querySelector(".u062-caps");
  const go = root.querySelector(".u062-go");
  const welcomeTitle = document.getElementById("u062WelcomeTitle");
  const welcomeSub = document.getElementById("u062WelcomeSub");
  const back = hi.querySelector("button");
  const helperLink = root.querySelector(".u062-row a");

  const uid = "u062-" + Math.random().toString(36).slice(2, 7);
  root.querySelectorAll(".u062-login .u062-f").forEach((f, i) => {
    const inp = f.querySelector("input");
    inp.id = `${uid}-${i}`;
    f.querySelector("label").htmlFor = inp.id;
  });
  err.id = `${uid}-err`;
  pw.setAttribute("aria-describedby", err.id);

  let busy = false;
  let timer = 0;

  function resolveNextUrl() {
    const next = new URLSearchParams(window.location.search).get("next") || "";
    if (next.startsWith("/") && !next.startsWith("//")) return next;
    return "/tbsgagtech/v1/overview";
  }

  eye.addEventListener("click", () => {
    const on = eye.getAttribute("aria-pressed") !== "true";
    eye.setAttribute("aria-pressed", String(on));
    eye.setAttribute("aria-label", on ? "Ẩn mật khẩu" : "Hiện mật khẩu");
    pw.type = on ? "text" : "password";
  });

  pw.addEventListener("keyup", (e) => {
    if (e.getModifierState) caps.classList.toggle("on", e.getModifierState("CapsLock"));
  });

  pw.addEventListener("input", () => {
    pwF.classList.remove("bad");
    pw.removeAttribute("aria-invalid");
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (busy) return;
    busy = true;
    go.classList.add("busy");
    go.setAttribute("aria-label", "Đang kiểm tra");

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: emailInput.value.trim(),
          password: pw.value,
        }),
      });
      const data = await res.json().catch(() => ({}));

      timer = setTimeout(() => {
        if (!root.isConnected) return;
        go.classList.remove("busy");

        if (res.ok && data.ok) {
          go.classList.add("ok");
          go.setAttribute("aria-label", "Đăng nhập thành công");
          if (welcomeTitle) welcomeTitle.textContent = `Xin chào, ${data.user?.display_name || "Admin"}`;
          if (welcomeSub) {
            const fmtVnLogin = (raw) => {
              const d = new Date(raw);
              if (isNaN(d.getTime())) return String(raw).replace("T", " ").slice(0, 19);
              const vn = new Date(d.getTime() + 7 * 60 * 60 * 1000);
              return vn.toISOString().replace("T", " ").slice(0, 19);
            };
            welcomeSub.textContent = data.user?.last_login_utc
              ? `Lần trước: ${fmtVnLogin(data.user.last_login_utc)} UTC+7`
              : `${data.user?.email || ""} · ${data.user?.role || "ADMIN"}`;
          }
          timer = setTimeout(() => {
            if (!root.isConnected) return;
            root.classList.add("is-in");
            form.inert = true;
            hi.setAttribute("aria-hidden", "false");
            back.tabIndex = 0;
            back.focus({ preventScroll: true });
            timer = setTimeout(() => {
              window.location.href = resolveNextUrl();
            }, 900);
          }, 550);
          return;
        }

        busy = false;
        go.removeAttribute("aria-label");
        const left = Number(data.tries_left ?? 0);
        err.textContent = left > 0
          ? `Sai thông tin đăng nhập · Còn ${left} lần thử`
          : "Tạm giới hạn đăng nhập, vui lòng kiểm tra lại mật khẩu";
        pwF.classList.add("bad");
        pw.setAttribute("aria-invalid", "true");
        root.classList.remove("shake");
        void root.offsetWidth;
        root.classList.add("shake");
        pw.select();
      }, 650);
    } catch (_) {
      busy = false;
      go.classList.remove("busy");
      go.removeAttribute("aria-label");
      err.textContent = "Lỗi kết nối máy chủ xác thực";
      pwF.classList.add("bad");
      pw.setAttribute("aria-invalid", "true");
    }
  });

  root.addEventListener("animationend", (e) => {
    if (e.target === root) root.classList.remove("shake");
  });

  back.addEventListener("click", async () => {
    clearTimeout(timer);
    await fetch("/api/auth/logout", { method: "POST" }).catch(() => {});
    root.classList.remove("is-in");
    form.inert = false;
    hi.setAttribute("aria-hidden", "true");
    back.tabIndex = -1;
    go.classList.remove("ok");
    go.removeAttribute("aria-label");
    busy = false;
    pw.value = "";
    pwF.classList.remove("bad");
    pw.focus({ preventScroll: true });
  });

  if (helperLink) {
    helperLink.addEventListener("click", (e) => {
      e.preventDefault();
      err.textContent = "Liên hệ quản trị TBSG IT để cấp lại mật khẩu PBKDF2";
      pwF.classList.add("bad");
    });
  }
})();
