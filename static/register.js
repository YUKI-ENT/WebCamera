const form = document.querySelector("#registerForm");
const deviceName = document.querySelector("#deviceName");
const statusText = document.querySelector("#registerStatus");
const params = new URLSearchParams(window.location.search);
const registrationToken = params.get("token") || "";

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!registrationToken) {
    statusText.textContent = "登録用トークンがありません。サーバーGUIで登録QRを再発行してください。";
    return;
  }

  statusText.textContent = "登録中です...";
  try {
    const response = await fetch("/api/register-device", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        registration_token: registrationToken,
        device_name: deviceName.value.trim() || navigator.userAgent,
      }),
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || "登録に失敗しました。");
    }
    localStorage.setItem("webcamera_device_token", result.device_token);
    statusText.textContent = "登録しました。アップロード画面を開いて利用できます。";
  } catch (error) {
    statusText.textContent = error.message;
  }
});
