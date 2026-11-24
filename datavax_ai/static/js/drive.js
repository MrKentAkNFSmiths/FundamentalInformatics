/* Drive Explorer interactivity: uploads, folders, notes, star, rename, move, delete, share */

document.addEventListener("DOMContentLoaded", () => {
  const workspace = document.getElementById("driveWorkspace");
  if (!workspace) return;

  const currentFolderUuid = workspace.getAttribute("data-folder-uuid");
  const uploadUrl = workspace.getAttribute("data-upload-url");
  const filesGrid = document.getElementById("filesGrid");
  const viewToggleBtn = document.getElementById("viewModeToggleBtn");
  const fileUploadInput = document.getElementById("driveFileInput");
  const triggerUploadBtn = document.getElementById("triggerUploadBtn");

  const VIEW_KEY = "datavax_drive_view";
  if (filesGrid && localStorage.getItem(VIEW_KEY) === "list") {
    filesGrid.classList.add("list-view");
  }
  if (viewToggleBtn && filesGrid) {
    viewToggleBtn.addEventListener("click", () => {
      filesGrid.classList.toggle("list-view");
      localStorage.setItem(VIEW_KEY, filesGrid.classList.contains("list-view") ? "list" : "grid");
    });
  }

  if (triggerUploadBtn && fileUploadInput) {
    triggerUploadBtn.addEventListener("click", () => fileUploadInput.click());
    fileUploadInput.addEventListener("change", () => {
      if (fileUploadInput.files?.length) {
        uploadFileList(fileUploadInput.files);
      }
    });
  }

  ["dragenter", "dragover"].forEach((ev) => {
    workspace.addEventListener(ev, (e) => {
      e.preventDefault();
      workspace.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach((ev) => {
    workspace.addEventListener(ev, (e) => {
      e.preventDefault();
      workspace.classList.remove("dragover");
    });
  });
  workspace.addEventListener("drop", (e) => {
    const files = e.dataTransfer?.files;
    if (files && files.length > 0) {
      uploadFileList(files);
    }
  });

  async function uploadFileList(fileList) {
    const fd = new FormData();
    fd.append("folder_uuid", currentFolderUuid);
    Array.from(fileList).forEach((f) => fd.append("files", f));
    try {
      window.DataVax.showToast(`Загрузка файлов (${fileList.length})...`, "info");
      const data = await window.DataVax.postForm(uploadUrl, fd);
      window.DataVax.showToast(data.message || "Файлы загружены", "success");
      window.location.reload();
    } catch (err) {
      window.DataVax.showToast(err.message, "error");
    }
  }

  // Modal openers
  document.getElementById("openNewFolderBtn")?.addEventListener("click", () => {
    window.DataVax.openModal("newFolderModal");
  });
  document.getElementById("openNewNoteBtn")?.addEventListener("click", () => {
    window.DataVax.openModal("newNoteModal");
  });

  // New folder form
  document.getElementById("newFolderForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    try {
      const data = await window.DataVax.postForm(form.action, new FormData(form));
      window.DataVax.showToast(data.message, "success");
      window.location.reload();
    } catch (err) {
      window.DataVax.showToast(err.message, "error");
    }
  });

  // New note form
  document.getElementById("newNoteForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    try {
      const data = await window.DataVax.postForm(form.action, new FormData(form));
      window.DataVax.showToast(data.message, "success");
      if (data.file?.preview_url) {
        window.location.href = data.file.preview_url;
      } else {
        window.location.reload();
      }
    } catch (err) {
      window.DataVax.showToast(err.message, "error");
    }
  });

  // Star toggle
  document.querySelectorAll("[data-star-url]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const url = btn.getAttribute("data-star-url");
      try {
        const data = await window.DataVax.postForm(url, new FormData());
        btn.classList.toggle("starred", Boolean(data.is_starred));
      } catch (err) {
        window.DataVax.showToast(err.message, "error");
      }
    });
  });

  // Rename modal
  const renameForm = document.getElementById("renameForm");
  const renameInput = document.getElementById("renameInput");
  document.querySelectorAll("[data-rename-url]").forEach((btn) => {
    btn.addEventListener("click", () => {
      renameForm.action = btn.getAttribute("data-rename-url");
      renameInput.value = btn.getAttribute("data-current-name") || "";
      window.DataVax.openModal("renameModal");
      setTimeout(() => renameInput.focus(), 50);
    });
  });
  renameForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const data = await window.DataVax.postForm(renameForm.action, new FormData(renameForm));
      window.DataVax.showToast(data.message, "success");
      window.location.reload();
    } catch (err) {
      window.DataVax.showToast(err.message, "error");
    }
  });

  // Move modal
  const moveForm = document.getElementById("moveForm");
  document.querySelectorAll("[data-move-url]").forEach((btn) => {
    btn.addEventListener("click", () => {
      moveForm.action = btn.getAttribute("data-move-url");
      window.DataVax.openModal("moveModal");
    });
  });
  moveForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const data = await window.DataVax.postForm(moveForm.action, new FormData(moveForm));
      window.DataVax.showToast(data.message, "success");
      window.location.reload();
    } catch (err) {
      window.DataVax.showToast(err.message, "error");
    }
  });

  // Delete item
  document.querySelectorAll("[data-delete-url]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const url = btn.getAttribute("data-delete-url");
      const label = btn.getAttribute("data-item-name") || "объект";
      if (!confirm(`Удалить «${label}»? Это действие нельзя отменить.`)) return;
      try {
        const data = await window.DataVax.postForm(url, new FormData());
        window.DataVax.showToast(data.message || "Удалено", "success");
        window.location.reload();
      } catch (err) {
        window.DataVax.showToast(err.message, "error");
      }
    });
  });

  // Share from Drive modal
  const shareForm = document.getElementById("driveShareForm");
  const shareResultBox = document.getElementById("driveShareResult");
  const shareResultLink = document.getElementById("driveShareLinkInput");
  document.querySelectorAll("[data-share-url]").forEach((btn) => {
    btn.addEventListener("click", () => {
      shareForm.action = btn.getAttribute("data-share-url");
      document.getElementById("driveShareTitle").value = btn.getAttribute("data-item-name") || "";
      document.getElementById("driveSharePassword").value = "";
      if (shareResultBox) shareResultBox.classList.add("hidden");
      window.DataVax.openModal("driveShareModal");
    });
  });
  shareForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const data = await window.DataVax.postForm(shareForm.action, new FormData(shareForm));
      if (shareResultBox && shareResultLink) {
        shareResultLink.value = data.share_url;
        shareResultBox.classList.remove("hidden");
      }
      window.DataVax.copyText(data.share_url, "Ссылка создана и скопирована!");
    } catch (err) {
      window.DataVax.showToast(err.message, "error");
    }
  });
  document.getElementById("copyDriveShareBtn")?.addEventListener("click", () => {
    if (shareResultLink?.value) {
      window.DataVax.copyText(shareResultLink.value);
    }
  });
});
