# System Cloned Voices Implementation Plan

> Historical plan: the protected system-profile design below was superseded by the [unified voice catalog](2026-09-13-unified-voice-catalog.md). The backend maintains built-in and cloned voices; every profile is editable and deletable. Offline installation adds voices only.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote the four approved clones into permanent system profiles and document a reproducible process for adding future voices.

**Architecture:** Persist registered voice definitions separately from user-editable profiles, with protected system profiles referencing stable registration keys. Compose registered and built-in capabilities in one synthesis catalog shared by profile routes, preview routes, and generation resolution. Provision existing enrollments through a local command; keep the production runtime independent of experiment modules.

**Tech Stack:** Python 3.11+, FastAPI, SQLite, existing Qwen realtime provider, plain JavaScript, pytest, Vitest.

**Spec:** [System cloned voices — phase one](../specs/2026-09-13-system-cloned-voices.md). The user's go-ahead approves the outline, including protected saved originals and Save As for personal variations.

**Planning update:** The user subsequently requested useful long-term names and durable enrollment scripts. Proposed names are Kai Narrator, Vivian Narrator, Bellona Narrator, and Neil Narrator. The [operator-tooling extension](2026-09-13-durable-voice-tooling.md) is a prerequisite work package for this plan. It supersedes the earlier recommendation to use a pinned experiment checkout for future voice creation; retain the old guide commands as historical reproduction instructions.

## Global Constraints

- Framework-free frontend; one FastAPI service and SQLite database.
- No changes to extraction, segmentation, playback stitching, or existing audio.
- No enrollment UI, automatic enrollment, retries, startup job recovery, voice design, or cloud deletion.
- No new generation-history schema or invented historical model metadata.
- All four system voices use English, `qwen3-tts-vc-realtime-2026-01-15`, and empty synthesis instructions.
- Reuse selections 16/Kai/1.0, 11/Vivian/1.1, 6/Bellona/1.25, and 1/Neil/1.0 from run `20260913T043114Z-0f3d936a`.
- Never commit credentials, account-specific enrollment manifests, reference recordings, or generated audio.
- Preserve existing browser selections, personal profiles, OCR drafts, generation snapshots, and audio.
- Do not switch the running checkout, mutate its database, or invoke paid providers during planning.

## File and responsibility map

| Files | Responsibility |
| --- | --- |
| New `src/tts_app/registered_voice_storage.py` | Registered definition types, schema, catalog installation, missing-system-profile restoration |
| Existing `profile_storage.py`, `storage.py` | System-key migration, protected ordinary profile operations, Storage composition |
| New `src/tts_app/voice_catalog_install.py` | Offline manifest validation, private reference copying, CLI and installation reporting |
| New `src/tts_app/synthesis_catalog.py` | Compose provider built-ins with registered capabilities |
| Existing `synthesis.py`, `generation_settings.py` | Shared validation and immutable request resolution |
| Existing `routes/voice_profiles.py`, `routes/voice_samples.py`, `api.py` | API protection, options metadata, dependency wiring |
| Existing `static/profile-editor.js`, `static/profile-selection.js`, `static/instruction-voice-sample.js` | Protected originals, Save As, selection and capability-aware editing |
| Existing `static/index.html`, `static/styles.css` | Accessible system designation, explanatory copy, cache-version changes |
| Existing `docs/cloned-voices.md` | Verified experimental cloning guide; extend with production installation |

Paths in the table are relative to `src/tts_app/` unless a full prefix is supplied. Test files are listed in each task. Leave the provider websocket transport and sample-cache implementation unchanged unless a focused test exposes a necessary integration defect.

## Task 1: Registered definitions and protected profile storage

**Files:** Create `src/tts_app/registered_voice_storage.py`, `tests/test_system_voice_storage.py`; modify `src/tts_app/profile_storage.py`, `src/tts_app/storage.py`, `tests/test_voice_profiles.py`, `docs/schema.sql`, `docs/data-model.md`.

**Interfaces:** Define the following in `registered_voice_storage.py`; expose the methods through `Storage` using the existing mixin pattern. `ProtectedVoiceProfileError` belongs in `profile_storage.py` and carries `profile_id`.

```python
from typing import Any, TypedDict

class RegisteredVoiceDefinition(TypedDict):
    system_key: str
    provider: str
    model: str
    voice: str
    language: str
    name: str
    speed: float
    instructions: str
    preview_text: str
    reference_path: str  # relative to settings.data_dir
    reference_sha256: str
    provenance: dict[str, Any]

# Storage methods:
# install_registered_voices(definitions: list[RegisteredVoiceDefinition]) -> list[dict]
# list_registered_voices(provider_name: str) -> list[RegisteredVoiceDefinition]
# ensure_system_profiles() -> None
```

- [ ] Add failing storage tests with a deterministic `definition` fixture using `provider='fake'`, a synthetic voice ID, `system_key='readvox-kai-v1'`, and a reference hash. Exercise the public storage boundary, not raw SQL for ordinary operations:

```python
def test_system_original_is_protected(storage, definition):
    from tts_app.profile_storage import ProtectedVoiceProfileError
    import pytest
    profile = storage.install_registered_voices([definition])[0]
    with pytest.raises(ProtectedVoiceProfileError):
        storage.delete_voice_profile(profile['id'])
    with pytest.raises(ProtectedVoiceProfileError):
        storage.save_voice_profile({**profile, 'speed': 1.25}, profile['id'])
    assert storage.get_voice_profile(profile['id'])['speed'] == 1.0

def test_install_is_idempotent(storage, definition):
    first = storage.install_registered_voices([definition])
    assert storage.install_registered_voices([definition]) == first
    assert len(storage.list_registered_voices('fake')) == 1
```

- [ ] Run `.venv/bin/pytest tests/test_system_voice_storage.py -q`; confirm failures identify absent registration/protection behavior.
- [ ] Add a one-time migration using the existing schema mechanism. Create `registered_voices(system_key TEXT PRIMARY KEY, provider TEXT NOT NULL, definition_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)` and add nullable `voice_profiles.system_key` with a unique partial index for non-null values. Serialize validated definitions to `definition_json`; the repeated key/provider columns are indexing fields and must agree with the definition. Keep existing IDs, names, timestamps, and rows unchanged.
- [ ] Implement installation as one transaction: preflight duplicate keys, invalid definitions, existing key/content mismatch, and case-insensitive name conflicts; insert registrations and matching profiles together. Identical definitions are no-ops. Ordinary profile creation always writes a null system key, regardless of extra values in the supplied dictionary. Ordinary update/delete checks the system key in the same transaction as its write and raises `ProtectedVoiceProfileError` for a protected row.
- [ ] Implement `ensure_system_profiles()` from registered definitions, only inserting absent system rows. Do not alter existing protected rows on startup or reseed deleted ordinary defaults. Add a corruption-repair fixture that removes a system profile with direct test SQL, then confirms restoration; also confirm deleting an ordinary default still stays deleted after restart.
- [ ] Add migration and data-safety tests: preexisting history, preferences, audio and personal profiles survive; changing an existing registration is rejected atomically; a conflicting personal name is untouched; a personal copy of a registered voice is deletable without removing the registration.
- [ ] Run `.venv/bin/pytest tests/test_system_voice_storage.py tests/test_voice_profiles.py tests/test_storage.py -q`, update schema/data-model documentation, review the storage/data-loss checklist, and commit `feat: add registered voices and protected system profiles` with only this task's files.

## Task 2: Offline promotion of the four approved enrollments

**Files:** Create `src/tts_app/voice_catalog_install.py`, `tests/test_voice_catalog_install.py`; extend `docs/cloned-voices.md`; modify `.gitignore` only if the existing `data/` rule does not cover the new asset directory.

**Interfaces:** Consume `RegisteredVoiceDefinition` and `Storage.install_registered_voices()` from Task 1. Produce this public function and command:

```python
def install_clone_manifest(
    manifest_path: Path, *, settings: Settings, storage: Storage, check_only: bool = False
) -> list[dict]:
    """Validate an approved local comparison, copy reference assets, install profiles."""
```

```bash
.venv/bin/python -m tts_app.voice_catalog_install --manifest /absolute/path/to/manifest.json --check
.venv/bin/python -m tts_app.voice_catalog_install --manifest /absolute/path/to/manifest.json
```

- [ ] Write a temporary synthetic comparison manifest fixture with four short valid WAV references, the real selected numbers/default speeds, synthetic enrollment IDs, matching enrollment/track model, completed cloned tracks, and no paid calls. Test `--check` makes no filesystem or database changes; installation copies exact reference bytes and preserves the source; a second install preserves IDs and files.
- [ ] Run `.venv/bin/pytest tests/test_voice_catalog_install.py -q` and confirm the absent command/function is the failure.
- [ ] Implement strict source validation: approved selection mapping; matching pinned model; nonempty enrollment ID; completed cloned tracks; matching reference and synthesis speeds/provenance; readable mono 16-bit WAVs at least 24 kHz, 3–60 seconds and at most 10 MB; relative paths constrained to the manifest's experiment-data root, including symlink resolution; duplicate selection/key detection. Require the expected run ID for the initial four-voice import. A separately supplied future manifest must explicitly provide new system keys and display names through a documented `system_profiles` mapping, rather than accidentally reusing the initial keys.

  Define that mapping as string selection numbers to `{system_key, name}` objects, for example `{"system_profiles": {"1": {"system_key": "readvox-elias-v1", "name": "Elias"}}}`. Import exactly its mapped completed entries; reject unknown numbers and duplicate names/keys. The initial run uses the four keys/names in the spec without needing this field. Infer the audio root as the manifest's parent for root-level manifests, or its grandparent when the parent directory equals the declared run ID; reject any other layout. This explicitly supports both `latest.json` and `<run-id>/manifest.json` without the experimental runner's gallery-path limitation.
- [ ] Build definitions using the cloned-track model/speed and empty instructions. Use the reference text as editable preview text. Store source run ID, selection number, original preset/model/speed/instructions, enrollment request ID and reported fallback information in provenance. Reject a reported fallback-quality condition from unattended promotion with a clear message requiring a separately reviewed source; absence of a flag is recorded as absent.
- [ ] Stage copies beneath `settings.data_dir / 'voices'`; verify SHA-256 before atomic publication into a directory named by source manifest digest. Store reference paths relative to the data directory. Include the exact private source manifest for backup. Validate all database conflicts before publication; commit registrations/profiles together after asset publication. On a later database failure, report the retained unreferenced directory for explicit operator cleanup; never scan or delete preexisting artifacts. Crash/re-run tests must reuse matching staged/published content without overwriting different bytes.
- [ ] Add failures for wrong model, missing audio, traversal, checksum collision, name conflict, changed key content, invalid speed, incomplete enrollment, and database failure. Assert no partial registrations and no cloud calls. Document that this importer does not create enrollments, and that restoring the directory alone does not restore database metadata.
- [ ] Run `.venv/bin/pytest tests/test_voice_catalog_install.py tests/test_system_voice_storage.py -q`; perform the architecture checklist for asset ownership and atomicity; commit `feat: provision approved cloned voices from local manifests`.

## Task 3: Shared custom-voice capabilities and API integration

**Files:** Create `src/tts_app/synthesis_catalog.py`, `tests/test_synthesis_catalog.py`; modify `src/tts_app/synthesis.py`, `src/tts_app/generation_settings.py`, `src/tts_app/routes/voice_profiles.py`, `src/tts_app/routes/voice_samples.py`, `src/tts_app/api.py`, `tests/test_voice_profiles.py`, `tests/test_voice_samples.py`, `tests/test_ocr_api.py`.

**Interfaces:** Keep provider-specific websocket details in the existing provider. Define this generic composition entry point:

```python
def build_synthesis_catalog(
    provider, registered: list[RegisteredVoiceDefinition]
) -> InstructionSampleCapabilities:
    """Merge supported built-ins with registered voices for the active provider."""

# Revised validation boundary in synthesis.py:
# validate_synthesis(capabilities: InstructionSampleCapabilities, payload) -> None
# Revised route factories:
# create_voice_profile_router(storage, cache, capabilities)
# create_voice_sample_router(voice_sample_cache, capabilities)
```

`api.py` constructs capabilities from the active provider and `storage.list_registered_voices(settings.provider_name)` after schema/default initialization and `ensure_system_profiles()`. `resolve_generation_settings()` constructs the same catalog from its existing storage/provider arguments; stop constructing a sample cache merely to validate a generation. Registration is an operator operation requiring process reload before newly installed voices are exposed; there is no dynamic registration API.

- [ ] Add failing tests proving an installed synthetic custom voice can be previewed and saved, while an unregistered ID, mismatched model, wrong language and nonempty clone instructions fail before a provider call. Preserve existing built-in language compatibility: restrict only entries with an explicit language, and preserve the legacy flash model's existing en/zh behavior when composing its options.
- [ ] Run `.venv/bin/pytest tests/test_synthesis_catalog.py tests/test_voice_profiles.py tests/test_voice_samples.py -q` and inspect the failures.
- [ ] Compose one model entry with friendly `SelectOption` labels and language='en' for registered clones, `supports_instructions=False`, and exact enrolled voice IDs as values. Registration validation restricts this release's Qwen custom definitions to the pinned cloning model; fake-provider tests supply an equivalent deterministic definition. Never turn arbitrary request strings into supported capabilities.
- [ ] Update shared validation and every caller. Extend sample options additively with `model_capabilities: {model_id: {supports_instructions: bool}}` and `voice_languages_by_model: {model_id: {voice_id: [language_code]}}`; retain existing keys. API list/read/save responses expose derived `is_system`, `can_update`, and `can_delete`. Protect PUT/DELETE with HTTP 409 and detail code `system_profile_read_only`. Reject client-supplied `system_key` and privilege fields with 422, while continuing to accept ordinary editable request fields and existing harmless read-response fields used by old clients. The frontend serializes only editable fields.
- [ ] Add a parameterized generation test for Text, URL (mock extraction), and English OCR. Assert all provider calls receive the exact enrolled voice, pinned model, requested speed, English mapping, and empty instructions. Assert stored snapshots include all existing profile/synthesis fields. Chinese OCR mismatch must leave the draft unlinked and unchanged. Exercise ordinary clone derivatives edited/deleted after creation and confirm stored settings and later segment calls stay unchanged.
- [ ] Test legacy no-profile requests, existing instruction profiles, system PUT/DELETE rejection, forged system creation, and personal Save As creation. Test cache separation across voice/model/speed/text/instructions and sharing across names; clearing the cache must leave reference bytes, registrations, and profiles intact.
- [ ] Run `.venv/bin/pytest tests/test_synthesis_catalog.py tests/test_voice_profiles.py tests/test_voice_samples.py tests/test_ocr_api.py tests/test_generation.py -q`; review provider boundaries and request-before-mutation ordering; commit `feat: use registered cloned voices in previews and generation`.

## Task 4: System voices in the existing selector and editor

**Files:** Modify `src/tts_app/static/profile-editor.js`, `src/tts_app/static/profile-selection.js`, `src/tts_app/static/instruction-voice-sample.js`, `src/tts_app/static/index.html`, `src/tts_app/static/styles.css`, `tests/js/voice-profiles.test.js`, `tests/js/instruction-voice-sample.test.js`, `tests/test_frontend_static.py`.

**Interfaces:** Consume the additive profile permission fields and sample options from Task 3. Keep `createProfileEditor({onUse, onClose})`, `open(profile, available)`, and sample controller exports unchanged. Add one internal permission refresh function so async completion cannot accidentally reenable protected or unsupported controls.

- [ ] Add Vitest scenarios: opening a system original disables Save/Delete; Preview sends unsaved speed without POST/PUT profile writes; Save As posts editable values only and selects a new personal ID; failed Save As leaves the system ID selected; Cancel restores the saved original; busy-state restoration leaves Save/Delete disabled. Use the current DOM/fetch fixtures in the named-profile tests.
- [ ] Run `npm run test:js -- tests/js/voice-profiles.test.js tests/js/instruction-voice-sample.test.js` and confirm failures are the missing new behavior.
- [ ] Centralize editor permission calculation, with state equivalent to:

```javascript
save.disabled = busy || !id || !currentProfile.can_update;
remove.disabled = busy || !id || !currentProfile.can_delete;
saveAs.disabled = busy;
```

For older profile payloads without permission metadata, fall back to ordinary saved-profile behavior. Apply model-capability disabling after the general busy-state reset. Show the short system explanation beside top actions; preserve the existing selector position. Continue to allow unsaved editable settings as the source for Preview and Save As.
- [ ] Add model-change handling for empty clone instructions, per-model unsaved instruction drafts, and language-compatible voice choices. On profile load, reset transient per-model drafts from that saved profile. Test that switching back to an instruction model restores the session draft without leaking one profile's instructions into another.
- [ ] Add system designation with escaped text in both selectors. Retain existing persisted valid selections, use Kai only for missing English selection, and leave Chinese/OCR filtering unchanged. Ensure the profile summary uses a friendly registered-voice label instead of exposing the cloud ID. Test draft-preserving Edit/Cancel/Save As navigation from Text, URL, and Image, and direct `/voice-sample` entry.
- [ ] Run `npm run check:js`, `npm run lint:js`, `npm run test:js`, and `.venv/bin/pytest tests/test_frontend_static.py -q`. Inspect a fake-provider app at desktop and 390px mobile widths: no horizontal overflow, readable system explanation, logical keyboard focus, labeled controls and audible preview. Bump affected browser asset query versions together. Review frontend boundaries; commit `feat: expose protected system voices with personal Save As`.

## Task 5: Operator guide, full verification, and reviewable delivery

**Files:** Complete `docs/cloned-voices.md`; update `docs/architecture.md`, `docs/configuration.md`, `docs/operations.md`, `setup/README.md`, `tests/integration/test_qwen_voice_sample.py`, and focused documentation tests in `tests/test_docs.py`.

- [ ] Document initial provisioning with the two Task 2 commands, backup locations, collision resolution, account/region binding, and process reload after installation. Confirm current provider state using metadata only; never print credentials. Do not change `TTS_MODEL` to the cloning model. Preserve existing selected voices and old generations when installing.
- [ ] Document the future workflow in `docs/cloned-voices.md`: generate numbered reference candidates; record source preset/model/speed/instructions/text; listen and select; enroll once from the exact approved WAV; persist returned ID/target model/request ID immediately; compare at least three independent held-out passages; review fallback flags; listen at the intended speed; add a new stable key/name to the approved manifest's `system_profiles` mapping; run offline check/install; back up SQLite plus reference assets.
- [ ] Make the experimental steps reproducible without adding experimental pages to the production PR: document a separate operator checkout at commit `e6a031b` (on `experiment/qwen-session-consistency`) and the existing `tts_app.experiments.voice_gallery` / `tts_app.experiments.clone_lab` commands and their manifest files. For other candidates, identify the selected-number configuration in that pinned runner explicitly in the guide after reading it, and show the exact edit/command. Include a warning that a fresh clone-lab invocation creates new paid enrollments; `--resume <manifest>` reuses recorded IDs. If creation is interrupted before the ID is recorded, inspect the provider voice list by preferred name before any new enrollment. Link the primary provider API guidance; explain the observed audio-only enrollment workaround and why cloning synthesis sends empty instructions.

  After implementing the tooling extension, make its maintained commands the primary future-creation instructions. Keep the existing pinned commands in the historical section only. Expose Task 2's offline installer through `scripts/voices.py install`, including a versioned-manifest adapter and explicit `--accept` selection; the legacy module command can remain a compatibility entry point.
- [ ] Extend the existing single-request live canary with optional `QWEN_LIVE_CLONE_MANIFEST`. When set, import one approved definition/reference into `test_settings` temporary storage before app creation, select that system profile, and generate one text shorter than `segment_max_chars`. Assert one nonempty audio segment and exact snapshot model/voice/speed/empty instructions. When unset, retain the current saved-instruction-profile canary. Do not parameterize into multiple paid requests or create a cloud voice during tests.
- [ ] Run the full deterministic checks once after the final changes:

```bash
.venv/bin/pytest -q
npm run check:js
npm run lint:js
npm run test:js
git diff --check
```

- [ ] Run the one-voice live canary with the approved manifest path in `QWEN_LIVE_CLONE_MANIFEST` and local credentials. The following shell commands belong to implementation verification, not planning:

```bash
set -a
source .envrc.local
set +a
QWEN_LIVE_CLONE_MANIFEST=/home/mohan/tts/src/tts_app/static/clone-lab-data/latest.json RUN_QWEN_INTEGRATION=1 .venv/bin/pytest -m live_provider -q
```

The canary must verify the expected run ID before trusting the latest pointer and fail clearly if it changed. Test storage and resulting audio stay temporary.

- [ ] Run the architecture reviewer or simulate `docs/architecture-review-subagent.md` against the full production diff; fix findings. Verify all four catalog entries and reference hashes using the offline checker. Record that live testing covered one voice and subjective consistency still requires listening to production output.
- [ ] Commit `docs: document cloned voice provisioning and verification`. Prepare a production branch/PR based on `feat/named-voice-profiles` while #16 remains open; if it merges before implementation, base on updated main. Transfer only production commits and these planning documents from the experiment branch. Preserve all unrelated local files, particularly `hk-api.key`, and all ignored experiment assets. Use an isolated worktree during execution so intermediate commits do not reload the running app.
- [ ] For the later local rollout, first check that no generation is queued/generating, back up SQLite consistently and copy `data/voices/`, run the offline installer, then switch the running checkout to the reviewed branch. Use the existing development autoreload and verify loading; restart the service only if evidence shows autoreload is absent and no generation is active. The user requested planning in this turn, so rollout is not part of executing this document-writing task.

## Self-review and acceptance map

| Requirement | Owning tasks |
| --- | --- |
| Four exact approved clones; protected originals; stable IDs | 1, 2 |
| Durable reference assets, provenance, idempotent installation | 1, 2, 5 |
| Preview, Text/URL/OCR, speed and snapshot integrity | 3 |
| Save As, top actions, draft preservation, language selection | 4 |
| Cache clearing and deletion retain reference/audio data | 1, 3 |
| Future cloning process and deployment/account guidance | 5 |
| Deterministic checks, mobile/keyboard checks, live canary, architecture review | 1–5 |

The highest residual risks are account-bound cloud voice availability and subjective variation across separately synthesized segments. This phase preserves an exact known-good voice configuration and reports failures honestly; extraction and segmentation improvements remain a separately reviewable second phase.
