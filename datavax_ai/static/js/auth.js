/* Client-side live validation for sign-in and sign-up */

document.addEventListener("DOMContentLoaded", () => {
  const registerForm = document.getElementById("registerForm");
  if (!registerForm) return;

  const usernameInput = document.getElementById("username");
  const emailInput = document.getElementById("email");
  const p1Input = document.getElementById("password1");
  const p2Input = document.getElementById("password2");
  const submitBtn = document.getElementById("registerSubmitBtn");

  const uMsg = document.getElementById("usernameFeedback");
  const eMsg = document.getElementById("emailFeedback");
  const p1Msg = document.getElementById("password1Feedback");
  const p2Msg = document.getElementById("password2Feedback");

  const usernameRe = /^[a-zA-Z0-9._-]+$/;
  const emailRe = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  function setMsg(el, valid, text) {
    if (!el) return;
    el.textContent = text;
    el.className = valid ? "field-valid" : "field-error";
  }

  function validateAll() {
    const u = usernameInput.value.trim();
    const e = emailInput.value.trim();
    const p1 = p1Input.value;
    const p2 = p2Input.value;

    const uValid = u.length >= 3 && u.length <= 32 && usernameRe.test(u);
    const eValid = emailRe.test(e);
    const p1Valid = p1.length >= 8;
    const p2Valid = p2.length > 0 && p1 === p2;

    if (u.length > 0) {
      setMsg(
        uMsg,
        uValid,
        uValid ? "Логин подходит" : "От 3 до 32 символов (латиница, цифры, . _ -)"
      );
    } else if (uMsg) {
      uMsg.textContent = "";
    }

    if (e.length > 0) {
      setMsg(eMsg, eValid, eValid ? "Email корректен" : "Введите корректный email");
    } else if (eMsg) {
      eMsg.textContent = "";
    }

    if (p1.length > 0) {
      setMsg(p1Msg, p1Valid, p1Valid ? "Надёжная длина" : "Минимум 8 символов");
    } else if (p1Msg) {
      p1Msg.textContent = "";
    }

    if (p2.length > 0) {
      setMsg(p2Msg, p2Valid, p2Valid ? "Пароли совпадают" : "Пароли не совпадают");
    } else if (p2Msg) {
      p2Msg.textContent = "";
    }

    if (submitBtn) {
      submitBtn.disabled = !(uValid && eValid && p1Valid && p2Valid);
    }
  }

  [usernameInput, emailInput, p1Input, p2Input].forEach((input) => {
    if (input) input.addEventListener("input", validateAll);
  });
  validateAll();
});
