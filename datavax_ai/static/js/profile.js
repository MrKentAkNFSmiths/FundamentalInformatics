/* Profile avatar upload, nickname/bio inline editing, and share delete */

document.addEventListener("DOMContentLoaded", () => {
  const avatarBox = document.getElementById("profileAvatarBox");
  const avatarInput = document.getElementById("avatarUploadInput");

  if (avatarBox && avatarInput) {
    const uploadUrl = avatarBox.getAttribute("data-upload-url");
    avatarBox.addEventListener("click", () => avatarInput.click());
    avatarInput.addEventListener("change", async () => {
      const file = avatarInput.files?.[0];
      if (!file) return;
      const fd = new FormData();
      fd.append("avatar", file);
      try {
        const data = await window.DataVax.postForm(uploadUrl, fd);
        window.DataVax.showToast("Аватар обновлён", "success");
        setTimeout(() => window.location.reload(), 450);
        if (data.avatar_url) {
          const img = avatarBox.querySelector("img");
          if (img) img.src = data.avatar_url;
        }
      } catch (err) {
        window.DataVax.showToast(err.message, "error");
      }
    });
  }

  const editToggleBtn = document.getElementById("editProfileBtn");
  const editPanel = document.getElementById("profileEditPanel");
  const cancelEditBtn = document.getElementById("cancelProfileEditBtn");
  const editForm = document.getElementById("profileEditForm");

  if (editToggleBtn && editPanel) {
    editToggleBtn.addEventListener("click", () => editPanel.classList.toggle("hidden"));
  }
  if (cancelEditBtn && editPanel) {
    cancelEditBtn.addEventListener("click", () => editPanel.classList.add("hidden"));
  }

  if (editForm) {
    editForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const updateUrl = editForm.getAttribute("data-update-url");
      const fd = new FormData(editForm);
      try {
        const data = await window.DataVax.postForm(updateUrl, fd);
        window.DataVax.showToast(data.message || "Профиль обновлён", "success");
        window.location.replace(data.new_url);
      } catch (err) {
        window.DataVax.showToast(err.message, "error");
      }
    });
  }

  document.querySelectorAll("[data-delete-share-url]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const url = btn.getAttribute("data-delete-share-url");
      const title = btn.getAttribute("data-share-title") || "шейр";
      if (!confirm(`Удалить «${title}»?`)) return;
      try {
        await window.DataVax.postForm(url, new FormData());
        window.DataVax.showToast("Шейр удалён", "success");
        btn.closest(".share-card")?.remove();
      } catch (err) {
        window.DataVax.showToast(err.message, "error");
      }
    });
  });
});
