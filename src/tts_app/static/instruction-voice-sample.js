import { responseErrorMessage } from "./api-client.js?v=long-samples-1";

const languageSelect = document.querySelector("#instruction-language");
const voiceSelect = document.querySelector("#instruction-voice");
const speedSelect = document.querySelector("#instruction-speed");
const promptInput = document.querySelector("#instruction-prompt");
const textInput = document.querySelector("#instruction-text");
const form = document.querySelector("#instruction-sample-form");
const sampleButton = document.querySelector("#instruction-sample");
const clearButton = document.querySelector("#clear-instruction-samples");
const statusLine = document.querySelector("#instruction-status");
const audio = document.querySelector("#instruction-audio");

let options = {voice_catalog: [], speeds: [], languages: []};
let objectUrl = null;
let previewEpoch = 0;
let editorBusy = false, previewBusy = false, clearBusy = false;
let savedVoice = null;
function selectedVoice() {
  return options.voice_catalog.find(voice => String(voice.id) === voiceSelect.value)
    || (String(savedVoice?.id) === voiceSelect.value ? savedVoice : null);
}
function supportsInstructions() {
  return selectedVoice()?.supports_instructions === true;
}
export function sampleSelectionError() {
  if (!voiceSelect.value) return 'Choose a voice for this language to preview or save.';
  if (!selectedVoice()?.available) return 'This voice is unavailable. Choose another voice.';
  if (!selectedVoice().languages.includes(languageSelect.value)) return 'This voice does not support the selected language.';
  return '';
}
function applyCapabilities() {
  promptInput.disabled = editorBusy || !supportsInstructions();
  sampleButton.disabled = editorBusy || previewBusy || Boolean(sampleSelectionError());
  clearButton.disabled = editorBusy || clearBusy;
  const note = document.querySelector('#instruction-capability-note');
  if (note) note.textContent = sampleSelectionError() || (supportsInstructions() ? '' : 'Instructions are unavailable for this voice.');
}
export function setSampleBusy(value) { editorBusy = value; applyCapabilities(); }
function changeLanguage() {
  renderVoiceOptions(voiceSelect.value);
  applyCapabilities();
}

function languageLabel(language) {
  return { en: "English", zh: "Chinese" }[language] || language || "Auto";
}

function renderLanguageOptions() {
  languageSelect.innerHTML = options.languages
    .map((language) => {
      const selected = language.value === (options.default_language || "en") ? " selected" : "";
      return `<option value="${escapeHtml(language.value)}"${selected}>${escapeHtml(language.label || languageLabel(language.value))}</option>`;
    })
    .join("");
}

function renderVoiceOptions(voiceId = options.default_voice_id, preserveUnavailable = false) {
  const voices = options.voice_catalog.filter(voice => voice.available && voice.languages.includes(languageSelect.value));
  if (preserveUnavailable && savedVoice && !savedVoice.available && !voices.some(voice => voice.id === savedVoice.id)) voices.push(savedVoice);
  const placeholder = voices.length ? 'Choose a voice' : 'No voices available for this language';
  voiceSelect.innerHTML = `<option value="">${placeholder}</option>` + voices.map(voice => {
    const provider = {qwen: 'Qwen', fake: 'Fake'}[voice.provider] || voice.provider || '';
    const label = [voice.name, provider, voice.kind === 'cloned' ? 'Cloned' : ''].filter(Boolean).join(' · ');
    return `<option value="${escapeHtml(voice.id)}">${escapeHtml(label)}${voice.available ? '' : ' (unavailable)'}</option>`;
  }).join('');
  voiceSelect.value = voices.some(voice => String(voice.id) === String(voiceId)) ? String(voiceId) : '';
}

function renderSpeedOptions() {
  speedSelect.innerHTML = options.speeds
    .map((speed) => {
      const selected = Number(speed.value) === Number(options.default_speed || 1) ? " selected" : "";
      return `<option value="${escapeHtml(speed.value)}"${selected}>${escapeHtml(speed.label)}</option>`;
    })
    .join("");
}

function clearObjectUrl() {
  if (objectUrl) {
    URL.revokeObjectURL(objectUrl);
    objectUrl = null;
  }
}

async function loadOptions() {
  const response = await fetch("/api/voice-sample/options");
  if (!response.ok) {
    throw new Error("options failed");
  }
  options = await response.json();
  renderLanguageOptions();
  renderVoiceOptions();
  renderSpeedOptions();
  applyCapabilities();
  return options;
}

async function playInstructionSample(event) {
  event.preventDefault();
  if (editorBusy || previewBusy || sampleSelectionError()) return;
  const epoch = ++previewEpoch;
  const payload = {
    voice_id: Number(voiceSelect.value),
    speed: Number(speedSelect.value || "1"),
    language: languageSelect.value || "en",
    sample_text: textInput.value,
    instructions: supportsInstructions() ? promptInput.value : '',
  };
  previewBusy = true;
  applyCapabilities();
  statusLine.textContent = "Generating sample...";
  try {
    const response = await fetch("/api/voice-sample/instruction", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      statusLine.textContent = await responseErrorMessage(response, "Unable to load voice sample");
      return;
    }
    const blob = await response.blob();
    if (epoch !== previewEpoch) return;
    clearObjectUrl();
    objectUrl = URL.createObjectURL(blob);
    audio.src = objectUrl;
    await audio.play();
    statusLine.textContent = "Playing sample";
  } catch {
    statusLine.textContent = "Unable to load voice sample";
  } finally {
    previewBusy = false;
    applyCapabilities();
  }
}

async function clearSampleCache() {
  stopSamplePlayback();
  clearBusy = true;
  applyCapabilities();
  statusLine.textContent = "Clearing samples...";
  try {
    const response = await fetch("/api/voice-samples/cache", { method: "DELETE" });
    if (!response.ok) {
      statusLine.textContent = "Unable to clear samples";
      return;
    }
    clearObjectUrl();
    audio.removeAttribute("src");
    audio.load();
    statusLine.textContent = "Samples cleared";
  } catch {
    statusLine.textContent = "Unable to clear samples";
  } finally {
    clearBusy = false;
    applyCapabilities();
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

form?.addEventListener("submit", playInstructionSample);
clearButton?.addEventListener("click", clearSampleCache);
languageSelect?.addEventListener("change", changeLanguage);
voiceSelect?.addEventListener("change", applyCapabilities);

export const sampleReady = loadOptions().then(() => options).catch(() => {
  statusLine.textContent = "Unable to load voice options";
});

export async function refreshSampleOptions() {
  await sampleReady;
  return loadOptions();
}

export function sampleValues() {
  return {voice_id: voiceSelect.value ? Number(voiceSelect.value) : null, language: languageSelect.value,
    speed: Number(speedSelect.value || 1), instructions: supportsInstructions() ? promptInput.value : '', preview_text: textInput.value};
}
export function setSampleValues(profile) {
  savedVoice = options.voice_catalog.find(voice => String(voice.id) === String(profile.voice_id)) || {
    id: profile.voice_id, name: profile.voice_name || profile.voice || 'Saved voice', provider: profile.provider,
    available: false, languages: [profile.language], supports_instructions: false,
  };
  languageSelect.value = profile.language;
  renderVoiceOptions(profile.voice_id, Boolean(profile.voice_id));
  if (![...speedSelect.options].some(option => Number(option.value) === Number(profile.speed))) {
    const option = document.createElement('option');
    option.value = String(profile.speed); option.textContent = `${profile.speed}x`;
    speedSelect.append(option);
  }
  speedSelect.value = String(profile.speed);
  promptInput.value = profile.instructions || '';
  textInput.value = profile.preview_text;
  applyCapabilities();
}
export function stopSamplePlayback() { previewEpoch += 1; audio.pause(); }
