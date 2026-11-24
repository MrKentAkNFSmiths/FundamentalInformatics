/* Unified Share Editor (/new/): CodeMirror + File Drop + Remote URL */

document.addEventListener("DOMContentLoaded", () => {
  const editorTextarea = document.getElementById("codeEditorTextarea");
  if (!editorTextarea) return;

  const DRAFT_KEY = "datavax_editor_draft_v2";
  const LANG_KEY = "datavax_editor_lang_v2";
  const MAX_FILE_BYTES = parseInt(editorTextarea.getAttribute("data-max-bytes") || String(100 * 1024 * 1024), 10);

  const cm = CodeMirror.fromTextArea(editorTextarea, {
    mode: "text",
    theme: "tomorrow-night-eighties",
    lineNumbers: true,
    matchBrackets: true,
    autoCloseBrackets: true,
    lineWrapping: true,
    tabSize: 4,
  });

  const langSelect = document.getElementById("languageSelect");
  const savedLang = localStorage.getItem(LANG_KEY);
  if (savedLang && langSelect) {
    langSelect.value = savedLang;
    cm.setOption("mode", savedLang);
  }
  const savedDraft = localStorage.getItem(DRAFT_KEY);
  if (savedDraft) {
    cm.setValue(savedDraft);
  }

  cm.on("change", () => {
    localStorage.setItem(DRAFT_KEY, cm.getValue());
  });

  langSelect?.addEventListener("change", () => {
    cm.setOption("mode", langSelect.value);
    localStorage.setItem(LANG_KEY, langSelect.value);
  });

  let activeTab = "code";
  const tabBtns = document.querySelectorAll("[data-editor-tab]");
  const panels = {
    code: document.getElementById("tabPanelCode"),
    file: document.getElementById("tabPanelFile"),
    url: document.getElementById("tabPanelUrl"),
  };

  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      activeTab = btn.getAttribute("data-editor-tab");
      tabBtns.forEach((b) => b.classList.toggle("active", b === btn));
      Object.entries(panels).forEach(([key, panel]) => {
        if (panel) panel.classList.toggle("hidden", key !== activeTab);
      });
      if (activeTab === "code") {
        setTimeout(() => cm.refresh(), 10);
      }
    });
  });

  // File upload mode
  let selectedFile = null;
  const dropArea = document.getElementById("editorFileDrop");
  const fileInput = document.getElementById("editorFileInput");
  const fileMeta = document.getElementById("editorFileSelected");
  const titleInput = document.getElementById("shareTitleInput");

  function setSelectedFile(file) {
    if (!file) return;
    if (file.size > MAX_FILE_BYTES) {
      window.DataVax.showToast("Файл превышает максимально допустимый размер", "error");
      return;
    }
    selectedFile = file;
    if (fileMeta) {
      fileMeta.textContent = `${file.name} (${(file.size / 1024).toFixed(1)} КБ)`;
      fileMeta.classList.remove("hidden");
    }
    if (titleInput && !titleInput.value.trim()) {
      titleInput.value = file.name;
    }
  }

  if (dropArea && fileInput) {
    dropArea.addEventListener("click", () => fileInput.click());
    ["dragenter", "dragover"].forEach((ev) => {
      dropArea.addEventListener(ev, (e) => {
        e.preventDefault();
        dropArea.classList.add("dragover");
      });
    });
    ["dragleave", "drop"].forEach((ev) => {
      dropArea.addEventListener(ev, (e) => {
        e.preventDefault();
        dropArea.classList.remove("dragover");
      });
    });
    dropArea.addEventListener("drop", (e) => {
      if (e.dataTransfer?.files?.length) {
        setSelectedFile(e.dataTransfer.files[0]);
      }
    });
    fileInput.addEventListener("change", () => {
      if (fileInput.files?.length) {
        setSelectedFile(fileInput.files[0]);
      }
    });
  }

  // Password show/hide
  const pwdInput = document.getElementById("sharePasswordInput");
  document.getElementById("togglePwdVisibility")?.addEventListener("click", () => {
    if (!pwdInput) return;
    pwdInput.type = pwdInput.type === "password" ? "text" : "password";
  });

  // Submit share
  const submitBtn = document.getElementById("publishShareBtn");
  submitBtn?.addEventListener("click", async () => {
    const uploadUrl = submitBtn.getAttribute("data-upload-url");
    const fd = new FormData();

    const title = titleInput?.value.trim() || "";
    const description = document.getElementById("shareDescriptionInput")?.value.trim() || "";
    const password = pwdInput?.value || "";
    const expirePreset = document.getElementById("shareExpireSelect")?.value || "1d";
    const isAnonEl = document.getElementById("shareAnonymousCheck");
    const saveDriveEl = document.getElementById("shareSaveDriveCheck");

    fd.append("title", title);
    fd.append("description", description);
    fd.append("password", password);
    fd.append("expire_preset", expirePreset);
    if (isAnonEl) {
      fd.append("is_anonymous", isAnonEl.checked ? "true" : "false");
    }
    if (saveDriveEl) {
      fd.append("save_to_drive", saveDriveEl.checked ? "true" : "false");
    }

    if (activeTab === "code") {
      const code = cm.getValue();
      if (!code.trim()) {
        window.DataVax.showToast("Введите текст или код для публикации", "error");
        return;
      }
      fd.append("code_content", code);
      fd.append("language", langSelect?.value || "text");
    } else if (activeTab === "file") {
      if (!selectedFile) {
        window.DataVax.showToast("Выберите файл для загрузки", "error");
        return;
      }
      fd.append("uploaded_file", selectedFile);
    } else if (activeTab === "url") {
      const remoteUrl = document.getElementById("remoteUrlInput")?.value.trim() || "";
      if (!remoteUrl) {
        window.DataVax.showToast("Укажите URL файла", "error");
        return;
      }
      fd.append("remote_url", remoteUrl);
    }

    submitBtn.disabled = true;
    try {
      const data = await window.DataVax.postForm(uploadUrl, fd);
      if (activeTab === "code") {
        localStorage.removeItem(DRAFT_KEY);
      }
      window.DataVax.showToast("Шейр опубликован!", "success");
      window.location.href = data.redirect_url;
    } catch (err) {
      window.DataVax.showToast(err.message, "error");
      submitBtn.disabled = false;
    }
  });
});
