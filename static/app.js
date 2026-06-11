const form = document.querySelector("#uploadForm");
const imageInput = document.querySelector("#imageInput");
const preview = document.querySelector("#preview");
const sendButton = document.querySelector("#sendButton");
const statusText = document.querySelector("#status");
const uploadedLink = document.querySelector("#uploadedLink");
const useRsbase = document.querySelector("#useRsbase");
const manualId = document.querySelector("#manualId");
const manualIdField = document.querySelector("#manualIdField");
const linkedPatientId = document.querySelector("#linkedPatientId");
const linkedPatientName = document.querySelector("#linkedPatientName");
const examName = document.querySelector("#examName");

let currentPatient = { id: "", name: "", available: false };

function updateManualMode() {
  const linked = useRsbase.checked;
  manualIdField.hidden = linked;
  manualId.disabled = linked;
  manualId.required = !linked;
}

async function loadSettings() {
  try {
    const response = await fetch("/settings");
    const settings = await response.json();
    const names = settings.exam_names && settings.exam_names.length ? settings.exam_names : ["カメラ"];
    examName.replaceChildren(
      ...names.map((name) => {
        const option = document.createElement("option");
        option.value = name;
        option.textContent = name;
        return option;
      }),
    );
  } catch (error) {
    const option = document.createElement("option");
    option.value = "カメラ";
    option.textContent = "カメラ";
    examName.replaceChildren(option);
  }
}

async function refreshPatient() {
  try {
    const response = await fetch("/patient", { cache: "no-store" });
    currentPatient = await response.json();
  } catch (error) {
    currentPatient = { id: "", name: "", available: false, error: "通信できません。" };
  }

  linkedPatientId.textContent = currentPatient.id || "未取得";
  linkedPatientName.textContent = currentPatient.name || "未取得";
  linkedPatientId.classList.toggle("muted", !currentPatient.id);
  linkedPatientName.classList.toggle("muted", !currentPatient.name);
}

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

useRsbase.addEventListener("change", updateManualMode);

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const file = imageInput.files[0];
  if (!file) {
    statusText.textContent = "画像を選択してください。";
    return;
  }

  if (useRsbase.checked && !currentPatient.id) {
    statusText.textContent = currentPatient.error || "RSBase IDを取得できません。";
    return;
  }

  if (!useRsbase.checked && !manualId.value.trim()) {
    statusText.textContent = "手動IDを入力してください。";
    return;
  }

  const formData = new FormData();
  formData.append("image", file);
  formData.append("use_rsbase", useRsbase.checked ? "true" : "false");
  formData.append("manual_id", manualId.value.trim());
  formData.append("exam_name", examName.value);

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

    statusText.textContent = `${result.message} ${result.filename}`;
    uploadedLink.href = result.url;
    uploadedLink.hidden = false;
  } catch (error) {
    statusText.textContent = error.message;
  } finally {
    sendButton.disabled = false;
  }
});

updateManualMode();
loadSettings();
refreshPatient();
setInterval(refreshPatient, 1000);
