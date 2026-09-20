import { escapeHtml } from './utils.js?v=playback-progress-1';
import { clearSamplePlayback } from './voice-controls.js?v=long-samples-1';
export { clearSamplePlayback };

const languageSelect = document.querySelector('#language-select');
const selector = document.querySelector('#profile-select');
const key = 'readvox.profileSelection.v1';
let profiles = [];
let inputMode = 'text';
let editProfile = () => {};
let selectionChanged = () => {};

function readSelection() {
  try {
    const value = JSON.parse(window.localStorage.getItem(key) || '{}');
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  } catch { return {}; }
}
function remember(profile) {
  if (!profile) return;
  try {
    window.localStorage.setItem(key, JSON.stringify({...readSelection(), [profile.language]: profile.id, language: profile.language}));
  } catch { /* Selection still works when browser storage is unavailable. */ }
}
export function currentLanguage() { return languageSelect?.value || 'en'; }
export function selectedProfile() { return profiles.find(profile => String(profile.id) === selector?.value); }
function availableProfile(profile) { return profile && profile.voice_available !== false && profile.voice_available !== 0; }
export function hasUsableSelectedProfile() { return Boolean(availableProfile(selectedProfile())); }
export function voiceGenerationPayload() {
  const profile = selectedProfile();
  if (!profile) throw new Error('Create a voice profile before generating audio');
  if (!availableProfile(profile)) throw new Error('This profile’s voice is unavailable. Choose another profile or use Edit to change its voice.');
  return {profile_id: profile.id};
}
export function renderVoiceControls({language} = {}) {
  if (!selector) return;
  languageSelect.value = language || currentLanguage() || readSelection().language || 'en';
  const matching = inputMode === 'image' ? profiles.filter(profile => profile.language === currentLanguage()) : profiles;
  const selected = matching.find(profile => profile.id === readSelection()[currentLanguage()])
    || matching.find(profile => profile.language === currentLanguage() && availableProfile(profile))
    || matching.find(availableProfile) || matching[0];
  selector.innerHTML = (matching.length ? '' : '<option value="">No saved profiles</option>') + matching.map(profile => `<option value="${profile.id}">${escapeHtml(profile.name)}</option>`).join('');
  if (selected) selector.value = String(selected.id);
  rememberSelection();
}
function rememberSelection() {
  const profile = selectedProfile();
  if (profile && inputMode !== 'image') languageSelect.value = profile.language;
  remember(profile);
  const summary = document.querySelector('#profile-summary');
  if (summary) {
    const language = currentLanguage() === 'zh' ? 'Chinese' : 'English';
    summary.textContent = !profile
      ? `No ${inputMode === 'image' ? `${language} ` : ''}profiles available. Choose Edit to create a profile.`
      : !availableProfile(profile)
        ? 'This profile’s voice is unavailable. Choose another profile or use Edit to change its voice.'
        : `${profile.speed}× · ${profile.language === 'zh' ? 'Chinese' : 'English'}`;
  }
  selectionChanged();
}
export async function loadProfiles(useProfile = null, {language} = {}) {
  const response = await fetch('/api/voice-profiles');
  if (!response.ok) throw new Error('Unable to load voice profiles');
  const previous = selectedProfile();
  profiles = await response.json();
  if (useProfile) remember(useProfile);
  renderVoiceControls({language: language || useProfile?.language || currentLanguage()});
  if (useProfile && language && useProfile.language !== language) {
    document.querySelector("#profile-status").textContent = "Profile saved. Image recognition language is unchanged; select a matching voice profile for this draft.";
  }
  if (previous && !profiles.some(profile => profile.id === previous.id)) {
    document.querySelector('#profile-status').textContent = hasUsableSelectedProfile()
      ? 'The selected profile was deleted. Using the available language default.'
      : 'The selected profile was deleted. Choose Edit to create a profile.';
  }
  return profiles;
}
export function setVoiceControlsHidden(hidden) { document.querySelector('#voice-panel')?.classList.toggle('hidden', hidden); }
export function registerVoiceControlEvents({onEdit, onChange} = {}) {
  editProfile = onEdit || editProfile;
  selectionChanged = onChange || selectionChanged;
  languageSelect?.addEventListener('change', () => renderVoiceControls());
  selector?.addEventListener('change', rememberSelection);
  document.querySelector('#voice-edit')?.addEventListener('click', () => editProfile(selectedProfile(), profiles));
  if (languageSelect) languageSelect.value = readSelection().language || 'en';
}

export async function refreshGenerationPayload() {
  await loadProfiles();
  return voiceGenerationPayload();
}

export function setVoiceInputMode(mode, {language} = {}) {
  inputMode = mode;
  document.querySelector('#ocr-language-field')?.classList.toggle('hidden', mode !== 'image');
  renderVoiceControls({language});
}
