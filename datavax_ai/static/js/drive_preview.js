/* Drive file preview and inline text/code editor */

document.addEventListener("DOMContentLoaded", () => {
  const codeArea = document.getElementById("driveCodeEditor");
  let cm = null;
  if (codeArea && typeof CodeMirror !== "undefined") {
    cm = CodeMirror.fromTextArea(codeArea, {
      mode: codeArea.getAttribute("data-mode") || "text",
      theme: "tomorrow-night-eighties",
      lineNumbers: true,
      lineWrapping: true,
      tabSize: 4,
    });
  }

  const saveContentBtn = document.getElementById("saveDriveContentBtn");
  if (saveContentBtn && cm) {
    saveContentBtn.addEventListener("click", async () => {
      const url = saveContentBtn.getAttribute("data-save-url");
      const fd = new FormData();
      fd.append("content", cm.getValue());
      saveContentBtn.disabled = true;
      try {
        const data = await window.DataVax.postForm(url, fd);
        window.DataVax.showToast(data.message || "Файл сохранён", "success");
      } catch (err) {
        window.DataVax.showToast(err.message, "error");
      } finally {
        saveContentBtn.disabled = false;
      }
    });
  }

  const shareForm = document.getElementById("previewShareForm");
  const shareResult = document.getElementById("previewShareResult");
  const shareLinkInput = document.getElementById("previewShareLink");

  document.getElementById("openPreviewShareModalBtn")?.addEventListener("click", () => {
    shareResult?.classList.add("hidden");
    window.DataVax.openModal("previewShareModal");
  });

  shareForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const data = await window.DataVax.postForm(shareForm.action, new FormData(shareForm));
      if (shareLinkInput && shareResult) {
        shareLinkInput.value = data.share_url;
        shareResult.classList.remove("hidden");
      }
      window.DataVax.copyText(data.share_url, "Ссылка создана и скопирована!");
    } catch (err) {
      window.DataVax.showToast(err.message, "error");
    }
  });

  document.getElementById("copyPreviewShareBtn")?.addEventListener("click", () => {
    if (shareLinkInput?.value) {
      window.DataVax.copyText(shareLinkInput.value);
    }
  });
});
