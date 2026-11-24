/* Shared DataVax UI utilities: CSRF, Toasts, Modals, Navbar, Clipboard */

window.DataVax = (() => {
  function getCSRFToken() {
    const cookie = document.cookie
      .split("; ")
      .find((row) => row.startsWith("csrftoken="));
    if (cookie) {
      return decodeURIComponent(cookie.split("=")[1]);
    }
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  }

  function showToast(message, type = "info") {
    const container = document.getElementById("toastContainer");
    if (!container) return;
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
      toast.remove();
    }, 3400);
  }

  async function copyText(text, successMsg = "Скопировано в буфер обмена") {
    try {
      await navigator.clipboard.writeText(text);
      showToast(successMsg, "success");
    } catch {
      const temp = document.createElement("textarea");
      temp.value = text;
      document.body.appendChild(temp);
      temp.select();
      document.execCommand("copy");
      temp.remove();
      showToast(successMsg, "success");
    }
  }

  function openModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.add("open");
  }

  function closeModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.remove("open");
  }

  async function postForm(url, formData) {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "X-CSRFToken": getCSRFToken(),
        "X-Requested-With": "XMLHttpRequest",
        Accept: "application/json",
      },
      body: formData,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.success === false) {
      throw new Error(data.error || "Ошибка выполнения запроса");
    }
    return data;
  }

  document.addEventListener("DOMContentLoaded", () => {
    const userPill = document.getElementById("userMenuBtn");
    const userDropdown = document.getElementById("userDropdown");
    if (userPill && userDropdown) {
      userPill.addEventListener("click", (e) => {
        e.stopPropagation();
        userDropdown.classList.toggle("open");
      });
      document.addEventListener("click", (e) => {
        if (!userDropdown.contains(e.target) && !userPill.contains(e.target)) {
          userDropdown.classList.remove("open");
        }
      });
    }

    const mobileBtn = document.getElementById("mobileMenuBtn");
    const mobileDrawer = document.getElementById("mobileDrawer");
    if (mobileBtn && mobileDrawer) {
      mobileBtn.addEventListener("click", () => {
        mobileDrawer.classList.toggle("open");
      });
    }

    document.querySelectorAll("[data-close-modal]").forEach((btn) => {
      btn.addEventListener("click", () => closeModal(btn.getAttribute("data-close-modal")));
    });

    document.querySelectorAll(".modal-backdrop").forEach((backdrop) => {
      backdrop.addEventListener("click", (e) => {
        if (e.target === backdrop) {
          backdrop.classList.remove("open");
        }
      });
    });

    document.querySelectorAll("[data-copy-text]").forEach((btn) => {
      btn.addEventListener("click", () => {
        copyText(btn.getAttribute("data-copy-text"));
      });
    });
  });

  return { getCSRFToken, showToast, copyText, openModal, closeModal, postForm };
})();
