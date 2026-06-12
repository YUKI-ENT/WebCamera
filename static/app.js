const form = document.querySelector("#uploadForm");
const photoInput = document.querySelector("#photoInput");
const galleryInput = document.querySelector("#galleryInput");
const videoInput = document.querySelector("#videoInput");
const previewGrid = document.querySelector("#previewGrid");
const imagePreview = document.querySelector("#imagePreview");
const videoPreview = document.querySelector("#videoPreview");
const sendButton = document.querySelector("#sendButton");
const statusText = document.querySelector("#status");
const uploadedLink = document.querySelector("#uploadedLink");
const useRsbase = document.querySelector("#useRsbase");
const manualId = document.querySelector("#manualId");
const manualIdField = document.querySelector("#manualIdField");
const linkedPatientId = document.querySelector("#linkedPatientId");
const linkedPatientName = document.querySelector("#linkedPatientName");
const examName = document.querySelector("#examName");
const modeBadge = document.querySelector("#modeBadge");
const manualHint = document.querySelector("#manualHint");

let currentPatient = { id: "", name: "", available: false };
let provisionalId = "999999";
let selectedFiles = [];
let selectedObjectUrls = [];

function updateManualMode() {
  const linked = useRsbase.checked;
  manualIdField.hidden = linked;
  manualId.disabled = linked;
  manualId.required = false;
  modeBadge.textContent = linked ? "ID連動" : "手動ID";
  modeBadge.classList.toggle("manual", !linked);
  if (manualHint) {
    manualHint.textContent = `RSBase ID連動がOFFです。空欄のまま保存すると仮ID ${provisionalId} を使用します。`;
  }
  if (linked) {
    manualId.value = "";
  }
}

async function loadSettings() {
  try {
    const response = await fetch("/settings");
    const settings = await response.json();
    const names = settings.exam_names && settings.exam_names.length ? settings.exam_names : ["カメラ"];
    provisionalId = settings.provisional_id || "999999";
    updateManualMode();
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

  linkedPatientId.textContent = currentPatient.id || `未取得 / 仮ID ${provisionalId}`;
  linkedPatientName.textContent = currentPatient.name || "未取得";
  linkedPatientId.classList.toggle("muted", !currentPatient.id);
  linkedPatientName.classList.toggle("muted", !currentPatient.name);
}

function revokeObjectUrls() {
  selectedObjectUrls.forEach((url) => URL.revokeObjectURL(url));
  selectedObjectUrls = [];
}

function clearPreviews() {
  revokeObjectUrls();
  previewGrid.hidden = true;
  previewGrid.replaceChildren();
  imagePreview.hidden = true;
  imagePreview.removeAttribute("src");
  videoPreview.hidden = true;
  videoPreview.pause();
  videoPreview.removeAttribute("src");
  videoPreview.load();
}

function resetOtherInputs(activeInput) {
  [photoInput, galleryInput, videoInput].forEach((input) => {
    if (input !== activeInput) {
      input.value = "";
    }
  });
}

function renderSinglePreview(file) {
  const url = URL.createObjectURL(file);
  selectedObjectUrls.push(url);

  if (file.type.startsWith("video/")) {
    videoPreview.src = url;
    videoPreview.hidden = false;
  } else {
    imagePreview.src = url;
    imagePreview.hidden = false;
  }
}

function renderGalleryPreview(files) {
  previewGrid.hidden = false;
  previewGrid.replaceChildren(
    ...files.slice(0, 12).map((file) => {
      const url = URL.createObjectURL(file);
      selectedObjectUrls.push(url);
      const item = document.createElement("div");
      item.className = "preview-item";

      const img = document.createElement("img");
      img.src = url;
      img.alt = file.name;
      item.appendChild(img);

      const label = document.createElement("span");
      label.textContent = file.name;
      item.appendChild(label);
      return item;
    }),
  );
}

function handleFileSelection(input, kindLabel) {
  const files = Array.from(input.files || []);
  uploadedLink.hidden = true;
  clearPreviews();
  resetOtherInputs(input);

  if (!files.length) {
    selectedFiles = [];
    sendButton.disabled = true;
    statusText.textContent = "";
    return;
  }

  selectedFiles = files;
  if (input === galleryInput && files.length > 1) {
    renderGalleryPreview(files);
  } else {
    renderSinglePreview(files[0]);
  }

  sendButton.disabled = false;
  const suffix = files.length === 1 ? files[0].name : `${files.length}件`;
  statusText.textContent = `${kindLabel}: ${suffix} を選択しました。`;
}

photoInput.addEventListener("change", () => handleFileSelection(photoInput, "写真"));
galleryInput.addEventListener("change", () => handleFileSelection(galleryInput, "ギャラリー"));
videoInput.addEventListener("change", () => handleFileSelection(videoInput, "動画"));
useRsbase.addEventListener("change", updateManualMode);

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  if (!selectedFiles.length) {
    statusText.textContent = "アップロードするファイルを選択してください。";
    return;
  }

  const formData = new FormData();
  selectedFiles.forEach((file) => formData.append("image", file));
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

    const count = result.count || 1;
    const prefix = result.used_provisional_id ? `仮ID ${result.patient_id} で保存しました。` : result.message;
    const firstFile = result.files && result.files.length ? result.files[0] : result;
    statusText.textContent = count === 1 ? `${prefix} ${firstFile.filename}` : `${prefix} ${count}件保存しました。`;
    uploadedLink.href = firstFile.url;
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
