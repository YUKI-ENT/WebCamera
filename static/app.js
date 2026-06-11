const form = document.querySelector("#uploadForm");
const imageInput = document.querySelector("#imageInput");
const preview = document.querySelector("#preview");
const sendButton = document.querySelector("#sendButton");
const statusText = document.querySelector("#status");
const uploadedLink = document.querySelector("#uploadedLink");

imageInput.addEventListener("change", () => {
  const file = imageInput.files[0];
  uploadedLink.hidden = true;

  if (!file) {
    preview.hidden = true;
    preview.removeAttribute("src");
    sendButton.disabled = true;
    statusText.textContent = "";
    return;
  }

  preview.src = URL.createObjectURL(file);
  preview.hidden = false;
  sendButton.disabled = false;
  statusText.textContent = `${file.name} を選択しました。`;
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const file = imageInput.files[0];
  if (!file) {
    statusText.textContent = "画像を選択してください。";
    return;
  }

  const formData = new FormData();
  formData.append("image", file);

  sendButton.disabled = true;
  statusText.textContent = "アップロード中です...";
  uploadedLink.hidden = true;

  try {
    const response = await fetch("/upload", {
      method: "POST",
      body: formData,
    });
    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.error || "アップロードに失敗しました。");
    }

    statusText.textContent = result.message;
    uploadedLink.href = result.url;
    uploadedLink.hidden = false;
  } catch (error) {
    statusText.textContent = error.message;
  } finally {
    sendButton.disabled = false;
  }
});
