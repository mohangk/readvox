# Unified voice catalog implementation plan

> Delivered historical design. The proposed [voice-owned models spec](../specs/2026-09-13-voice-owned-models.md) and [next implementation plan](2026-09-13-voice-owned-models.md) remove profile model selection and add explicit Qwen catalog population. That follow-up is planning only and has not changed the running app.

> **For agentic workers:** Use superpowers:subagent-driven-development to execute independently owned slices and review their interfaces.

**Goal:** Replace protected system profiles with editable profiles referring to a backend-managed provider voice catalog, then update PR17 and mark it ready.

**Architecture:** `voices` owns provider voice identity, display name, compatible model capabilities, availability and optional enrollment/reference provenance. `voice_profiles` owns voice_id plus model/language/speed/instructions/preview settings. Provider adapters supply built-in catalog entries; explicit installation supplies clones. Generations retain immutable snapshots. The configured provider must match a selected voice; no fallback to a different provider.

**Tech Stack:** Existing FastAPI, SQLite, framework-free JavaScript, pytest/Vitest.

**Spec:** User-approved conversation design: all profiles editable/deletable; voices maintained by backend, listed read-only in UI; model remains profile setting constrained by voice compatibility; future providers use the same data shape.

## Constraints

Preserve profile IDs/settings/timestamps, generations, audio/images, private clone IDs/reference bytes and legacy clients. No paid enrollment. Deleted profiles stay deleted across restart/reinstall. No system-profile protections, recovery templates or labels in runtime. Existing provider configuration remains unchanged. New providers require an adapter/configuration, never just an arbitrary database name.

## Interfaces

`voices`: id, key, provider, provider_voice_id, name, kind (builtin/cloned), available, models (JSON mapping model to label/languages/supports_instructions), metadata (JSON provenance), timestamps.

Public catalog records expose id/key/provider/provider_voice_id/name/kind/available and models array `{value,label,languages,supports_instructions}`. `/api/voices` is read-only; `/api/voice-sample/options` adds `voice_catalog` and `default_voice_id`. Private enrollment/reference metadata is not exposed.

Profile reads return voice_id, model, name, language, speed, instructions, preview_text plus derived provider/voice (legacy raw-ID alias)/voice_name/voice_key. New writes/previews use voice_id+model; legacy voice+model resolves within the active provider. Explicit conflicting identity fields fail. All generation paths snapshot provider, raw voice, friendly voice name and profile name once.

## Tasks

- [x] Storage/catalog: migration of registered_voices and old profiles, normalized CRUD/catalog, provider sync and unavailable retention; focused migration/persistence tests.
- [x] Runtime/API/installer: shared catalog validation and read API, legacy compatibility, generic provider isolation, immutable snapshots, preservation of existing clone profiles without creating or restoring profiles during installation; focused tests.
- [x] Frontend/History: catalog voice selection with compatible models, ordinary Save/Delete, concise Save/Save As explanation, historical profile label/search and escaped errors/names; focused JS/browser tests.
- [x] Docs/review/delivery: replace current system-profile guidance, full deterministic checks and one saved-clone live canary in temporary storage, architecture review, private backup+idle migration/autoreload, update PR17 description and mark ready (not draft).

## Delivered verification

385 deterministic Python tests passed (one opt-in live test skipped), 61 Vitest tests passed, and JavaScript syntax/lint and diff checks passed. The saved-clone Qwen canary made one successful synthesis request in temporary storage. Architecture review and its migration re-review passed. Fake-provider browser checks covered profile editing, preview, Save As, deletion, draft preservation, friendly historical labels, keyboard use and mobile/desktop layouts.

A rehearsal on a copy of the local database preserved all profiles and generations. The running checkout was updated while no generation was active; autoreload applied the migration. Post-rollout API/browser checks passed, and all 9 profile identities/settings, 45 generations and 2,536 audio/image/reference files were preserved. Private pre/post-migration backups are retained outside the repository. PR #17 was updated and marked ready for review.
