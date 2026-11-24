/* Home page quick dropzone and supported formats toggle */

document.addEventListener("DOMContentLoaded", () => {
  const toggleBtn = document.getElementById("formatsToggleBtn");
  const drawer = document.getElementById("formatsDrawer");
  if (toggleBtn && drawer) {
    toggleBtn.addEventListener("click", () => {
      drawer.classList.toggle("hidden");
    });
  }

  const dropzone = document.getElementById("quickDropzone");
  const fileInput = document.getElementById("quickFileInput");
  if (!dropzone || !fileInput) return;

  const uploadUrl = dropzone.getAttribute("data-upload-url");

  dropzone.addEventListener("click", () => fileInput.click());

  ["dragenter", "dragover"].forEach((ev) => {
    dropzone.addEventListener(ev, (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    });
  });

  ["dragleave", "drop"].forEach((ev) => {
    dropzone.addEventListener(ev, (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
    });
  });

  dropzone.addEventListener("drop", (e) => {
    const files = e.dataTransfer?.files;
    if (files && files.length > 0) {
      quickUpload(files[0]);
    }
  });

  fileInput.addEventListener("change", () => {
    if (fileInput.files && fileInput.files.length > 0) {
      quickUpload(fileInput.files[0]);
    }
  });

  async function quickUpload(file) {
    const formData = new FormData();
    formData.append("uploaded_file", file);
    formData.append("title", file.name);
    formData.append("expire_preset", "1d");
    try {
      window.DataVax.showToast(`Загрузка «${file.name}»...`, "info");
      const data = await window.DataVax.postForm(uploadUrl, formData);
      window.location.href = data.redirect_url;
    } catch (err) {
      window.DataVax.showToast(err.message, "error");
    }
  }
});
