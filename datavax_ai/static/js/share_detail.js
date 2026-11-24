/* Share detail interactions: CodeMirror read-only, Like, Copy, Save to Drive, Report, Delete */

document.addEventListener("DOMContentLoaded", () => {
  const codeArea = document.getElementById("shareCodePreview");
  let codeEditor = null;
  if (codeArea && typeof CodeMirror !== "undefined") {
    codeEditor = CodeMirror.fromTextArea(codeArea, {
      mode: codeArea.getAttribute("data-mode") || "text",
      theme: "tomorrow-night-eighties",
      lineNumbers: true,
      readOnly: true,
      lineWrapping: true,
    });
  }

  const likeBtn = document.getElementById("likeShareBtn");
  const likeCountEl = document.getElementById("likeShareCount");
  if (likeBtn && likeCountEl) {
    likeBtn.addEventListener("click", async () => {
      const url = likeBtn.getAttribute("data-like-url");
      try {
        const data = await window.DataVax.postForm(url, new FormData());
        likeCountEl.textContent = data.likes_count;
        likeBtn.classList.toggle("active", Boolean(data.liked));
      } catch (err) {
        window.DataVax.showToast(err.message, "error");
      }
    });
  }

  const copyContentBtn = document.getElementById("copyContentBtn");
  if (copyContentBtn) {
    copyContentBtn.addEventListener("click", () => {
      const textEl = document.getElementById("shareTextPreview");
      const content = codeEditor ? codeEditor.getValue() : textEl?.textContent || "";
      window.DataVax.copyText(content, "Содержимое скопировано");
    });
  }

  const saveDriveBtn = document.getElementById("saveToDriveBtn");
  if (saveDriveBtn) {
    saveDriveBtn.addEventListener("click", async () => {
      const url = saveDriveBtn.getAttribute("data-save-url");
      try {
        const data = await window.DataVax.postForm(url, new FormData());
        window.DataVax.showToast(data.message || "Сохранено в Мой диск", "success");
      } catch (err) {
        window.DataVax.showToast(err.message, "error");
      }
    });
  }

  document.getElementById("openReportModalBtn")?.addEventListener("click", () => {
    window.DataVax.openModal("reportModal");
  });

  const reportForm = document.getElementById("reportForm");
  reportForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const data = await window.DataVax.postForm(reportForm.action, new FormData(reportForm));
      window.DataVax.closeModal("reportModal");
      window.DataVax.showToast(data.message || "Жалоба отправлена", "success");
      reportForm.reset();
    } catch (err) {
      window.DataVax.showToast(err.message, "error");
    }
  });

  const deleteBtn = document.getElementById("deleteShareBtn");
  deleteBtn?.addEventListener("click", async () => {
    if (!confirm("Удалить этот шейр навсегда?")) return;
    const url = deleteBtn.getAttribute("data-delete-url");
    try {
      const data = await window.DataVax.postForm(url, new FormData());
      window.DataVax.showToast("Шейр удалён", "success");
      window.location.href = data.redirect_url || "/";
    } catch (err) {
      window.DataVax.showToast(err.message, "error");
    }
  });
});
