# Voice-owned models and catalog population implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans after implementation is authorized. Keep task ownership and review checkpoints explicit.

**Status:** Implemented, verified and loaded locally through autoreload. PR17 is ready for review with four logical commits.

**Goal:** Remove model selection from profiles and the editor, filter a unified voice list by language, and provide a repeatable Qwen catalog population/update script.

**Architecture:** A catalog voice owns one provider/model binding and flat language/instruction capabilities. Profiles reference `voice_id` and reading settings. An explicit offline command owns built-in catalog sync; clone installation uses the same schema. Preview and generation share resolution and retain generation snapshots.

**Tech Stack:** Existing FastAPI, SQLite migrations, framework-free JavaScript, argparse, pytest and Vitest.

**Spec:** [Voice-owned models and catalog population](../specs/2026-09-13-voice-owned-models.md). This is the binding specification and supersedes profile-owned models in the delivered catalog plan.

## Global constraints

- Implementation, verification, local rollout and PR17 updates are authorized. Consolidate only this PR branch's Git commits; preserve its base branch and existing generation History.
- Exactly one model per catalog voice; no model field/override in a named profile and no language-specific duplicate voice identities.
- Support app languages `en` and `zh`; one bilingual voice has `languages=["en","zh"]`.
- Keep all profiles editable/deletable, ordinary Save/Save As semantics, and OCR draft language independent.
- Keep provider protocol in adapters and snapshots immutable during a generation. No paid enrollment or automatic retries.
- The user permits removal of incompatible legacy voice/profile records; report concrete deletions and preserve independent History/media/reference assets.
- Population is offline, credential-free and Qwen-only in this phase. Updates consume reviewed definitions, not automatic online discovery.
- Retain the framework-free frontend and focused module boundaries. Remove obsolete branches and structures rather than layering another model selector/compatibility graph over them.

## Task 1: Flatten catalog/profile storage and migrate existing data

**Files:** `src/tts_app/voice_storage.py`, `voice_migrations.py`, `profile_storage.py`, `storage.py`, `voice_installation.py`, `voice_catalog_install.py`; `tests/test_voice_catalog_storage.py`, `test_voice_installation.py`, `test_voice_catalog_install.py`; `docs/schema.sql`, `docs/data-model.md`.

**Interfaces:** Catalog definitions have `key, provider, provider_voice_id, name, kind, available, model, languages, supports_instructions, metadata`. Stored records add ID/timestamps. Profile fields become `name, voice_id, language, speed, instructions, preview_text`; profile reads may join friendly identity fields but never a model. Existing `install_voices`, `get_voice`, `list_voices` and profile CRUD keep their behavior-level roles.

- [x] Add failing storage regressions proving one model on a voice and none in profile persistence/results. Use a synthetic bilingual voice and two profiles to verify one shared identity:

```python
def test_profiles_share_bilingual_voice_without_owning_model(storage, bilingual_voice):
    voice = storage.install_voices([bilingual_voice])[0]
    for language in ("en", "zh"):
        profile = storage.save_voice_profile(dict(
            name=language, voice_id=voice["id"], language=language,
            speed=1.1, instructions="", preview_text="Sample"))
        assert "model" not in profile
        assert profile["voice_id"] == voice["id"]
    assert len(storage.list_voices()) == 1
    assert voice["languages"] == ["en", "zh"]
```

- [x] Run the focused new tests and record the expected failures before schema changes.
- [x] Add one forward migration to flatten model capabilities and drop the profile model column. Preserve stable IDs/autoincrement and compatible reading settings; use the reviewed Qwen binding for built-ins and the enrolled model for clones. Produce a deterministic report for changed bindings/deleted incompatible records. Include old registry-to-catalog upgrades without retaining old runtime structures.
- [x] Test unsupported-language/instruction and unresolvable legacy records, no duplicate bilingual rows, invalid-source rollback, repeat initialization, and unchanged generation rows/reference bytes. Test that no profile reappears after deletion or reinstallation.
- [x] Adapt clone installation to emit a flat definition. Keep exact target model/reference/provenance validation, idempotency and catalog-only writes.
- [x] Run `.venv/bin/pytest tests/test_voice_catalog_storage.py tests/test_voice_installation.py tests/test_voice_catalog_install.py -q`; update schema documentation and commit the storage/installation slice.

## Task 2: Add Qwen source and catalog population command

**Files:** create `src/tts_app/providers/qwen_catalog.py`, `src/tts_app/voice_catalog_sync.py`, `scripts/populate_voice_catalog.py`, `tests/test_voice_catalog_sync.py`; modify `providers/options.py`, `providers/qwen.py`, `voice_storage.py`, `api.py`, `profile_defaults.py`, `setup/README.md`, `docs/configuration.md` and affected provider/default tests.

**Interfaces:** `qwen_voice_definitions()` emits the complete reviewed built-in definition list from Task 1. `sync_voice_catalog(settings, provider_name="qwen", check_only=False)` validates the source/target and returns target/schema-upgrade information plus stable-key lists of added, updated, unchanged and retired voices. The CLI resolves the checkout, loads settings, applies `--data-dir`, and invokes that helper. No provider client or credentials are needed. Keep Qwen source data separate from the generic SQLite sync operation; do not build a plugin/discovery framework.

- [x] Add failing command/service tests using temporary settings and injected synthetic definitions. Make production source injection a normal service parameter or monkeypatch its loader in tests; do not add test-only production behavior. Verify absent storage and no credential requirement:

```python
def test_check_does_not_create_target(tmp_path):
    target = tmp_path / "new-catalog"
    result = run_catalog_cli("--provider", "qwen", "--data-dir", str(target), "--check")
    assert result.returncode == 0
    assert not target.exists()
```

`run_catalog_cli` is a test helper wrapping `subprocess.run([sys.executable, "scripts/populate_voice_catalog.py", *args], capture_output=True, text=True, env=credential_free_environment)`; define it in this test module.

- [x] Verify the new tests fail before writing the script. Review the official Qwen preset list linked in the spec; encode each supported preset once with explicit model/languages and a source review date. Use instruction-family bindings where supported, existing flash-family bindings otherwise, and no automatic provider family upgrade.
- [x] Implement `--provider qwen`, `--data-dir` and `--check`. Validate all definitions before writes; on apply initialize/migrate and reconcile built-ins atomically. Preserve IDs/timestamps for no-ops, retain removed presets as unavailable, reject empty sources/duplicate identities/clone collisions, and leave other providers/clones/profiles untouched. Include changed model bindings in output.
- [x] Test populated-target refresh with one addition, one capability/model change, one retirement, a returning voice, an installed clone and another provider's voice. Check the exact scope of changes and full rollback on a late conflict. `--check` against old schema must inspect without upgrading it.
- [x] Remove unconditional startup synchronization. Seed ordinary default profiles only when the catalog has compatible voices and the one-time seeding marker is absent. Test empty-catalog startup and deletion remaining permanent. Keep fake catalog population explicit in test fixtures.
- [x] Remove duplicated English/Chinese preset definitions and obsolete catalog capability projection dependencies; retain only boundary-derived legacy options needed by supported non-editor callers.
- [x] Document fresh setup, source review/update then sync, clone bundle installation, read-only checks and the target path. Run `.venv/bin/pytest tests/test_voice_catalog_sync.py tests/test_api.py tests/test_docs.py -q`; commit the population/source slice.

## Task 3: Resolve voice-owned synthesis settings through the API

**Files:** `src/tts_app/voice_catalog.py`, `synthesis.py`, `synthesis_catalog.py`, `generation_settings.py`, `routes/voice_profiles.py`, `routes/voice_samples.py`, `api.py`, `profile_defaults.py`; `tests/test_catalog_voice_api.py`, `test_voice_profiles.py`, `test_voice_samples.py`, `test_synthesis_catalog.py`, `tests/integration/test_qwen_voice_sample.py`.

**Interfaces:** New profile/preview payloads omit model. The shared resolver consumes catalog identity and reading settings and returns the exact provider/raw voice/model plus validated settings. Public voices have flat `model, languages, supports_instructions`; editor options carry `voice_catalog`, language/speed choices and default voice IDs. New options no longer carry model lists or `voices_by_model`. Profile results expose no model.

- [x] Write failing API tests posting a profile and unsaved preview with only `voice_id`, language and reading settings. Assert provider calls use the catalog model and that profile GET has no model. Test wrong provider, unavailable voice, incompatible language/instructions, conflicting legacy identity/model and empty catalog.
- [x] Exercise Text, URL and OCR generation with the saved profile. Update/delete the profile and change the catalog binding after job creation; every segment must use the initial snapshot. Do not change generation-loop/provider code unless required to preserve that invariant.
- [x] Implement one resolver and use it in profile validation, preview and generation settings. Keep only small legacy input normalization; remove profile model override paths and obsolete internal multi-model projections. Preserve explicit no-profile generation behavior.
- [x] Test that a catalog model change yields a different preview cache entry while profile renaming does not; changing catalog language support rejects future incompatible requests without modifying the OCR draft.
- [x] Make options read the current catalog on request; verify a completed sync is reflected without restarting the service. Adapt the one-request live canary to create a profile without a model in temporary storage (do not run it until final deterministic checks pass).
- [x] Run `.venv/bin/pytest tests/test_catalog_voice_api.py tests/test_voice_profiles.py tests/test_voice_samples.py tests/test_synthesis_catalog.py -q`; commit the API/resolution slice.

## Task 4: Simplify editor and language filtering

**Files:** `src/tts_app/static/index.html`, `instruction-voice-sample.js`, `profile-editor.js`, `profile-selection.js`, `styles.css` as needed; `tests/js/voice-catalog.test.js`, `instruction-voice-sample.test.js`, `voice-profiles.test.js`, `tests/test_frontend_static.py`; cache-version references in imports/HTML.

**Interfaces:** Consume Task 3's flat voice fields. `sampleValues()` returns `voice_id, language, speed, instructions, preview_text`; loading a profile never reads model. Language filters availability/provider/voice language support. Keep existing navigation and saved browser profile selection interfaces.

- [x] Add failing Vitest tests showing a bilingual voice appears once in English and once in Chinese, an English-only clone is excluded in Chinese, provider names appear in labels, and Save/Preview payloads omit model.
- [x] Remove the model selector, model-change handlers, compatibility selection logic and per-model instruction draft maps. Move Language before Base voice and derive instruction capability directly from the selected voice.
- [x] Preserve a compatible voice when language changes. Clear an incompatible selection, show a prompt to choose a voice, and disable Preview/Save until valid. Test empty language choices, retired saved voices, async button state restoration and editable long preview text.
- [x] Retain the top Save/Save As/Cancel row and following profile selector. Verify Save As, Cancel, unsaved-preview behavior, persisted/missing selection, and Text/URL/OCR draft-preserving navigation.
- [x] Run `npm run check:js`, `npm run lint:js`, `npm run test:js` and `.venv/bin/pytest tests/test_frontend_static.py -q`; check 390/1440 layouts and keyboard flow using a temporary fake app; commit the frontend slice.

## Task 5: Review, documentation and eventual delivery

**Files:** `docs/architecture.md`, `docs/data-model.md`, `docs/schema.sql`, `docs/configuration.md`, `docs/cloned-voices.md`, `setup/README.md`, affected docs tests and this plan's completion record.

- [x] Audit the diff for simplification: no profile model column/derived field, no editor model selector/state, no catalog model lists, no recurring startup overwrite, and one canonical Qwen inventory with explicit language lists. Keep provider wire-level model inputs and generation snapshots intact.
- [x] Update durable documentation to describe the implemented schema and command, including population from empty, source review for new voices, optional reuse of the clone bundle and one-time default profile seeding. Mark older plans as historical without claiming this work is already delivered.
- [x] Rehearse migration and catalog population on a private copy of current data. List actual profile/voice deletions and binding changes, compare independent History/media/reference hashes, and verify repeat startup/sync do not recreate profiles. Use the user's cleanup authorization only for incompatible records.
- [x] Run `.venv/bin/pytest -q`, `npm run check:js`, `npm run lint:js`, `npm run test:js` and `git diff --check`. Run one live Qwen saved-profile canary with temporary storage and existing credentials/enrollment. Run architecture review against `docs/architecture-review-subagent.md` and resolve findings.
- [x] After implementation is authorized and verified, back up the live database/assets and wait until no generation is active before schema rollout. Use the existing autoreload checkout workflow and verify running language filtering, editable profiles, empty/catalog refresh behavior and friendly History names.
- [x] Update PR17 with the final implementation, validation and any actual cleanup, preserving its non-draft status. Mark these tasks complete only after their work is done.

## Verification record — 2026-09-13

- Deterministic verification: 410 Python tests passed, one opt-in live test skipped; JavaScript syntax/lint and all 65 Vitest tests passed; `git diff --check` clean.
- One live Qwen Kai saved-profile generation passed using temporary storage and the existing enrollment. No new enrollment or production audio was created.
- Architecture review passed after resolving migration provider context and consistent read-only database snapshot handling, including clone installer check/apply parity.
- Fake-provider browser checks passed for editing, Save/Save As, unsaved preview, language filtering, draft preservation, empty-catalog gating and catalog refresh without restart, keyboard controls, and 390/1440 layouts.
- Migration rehearsal preserved all 10 profiles and 45 generations; populated 52 catalog voices including four clones, with zero profile/voice deletions.

## Delivery record — 2026-09-13

- The running checkout uses the new schema and editor without a service restart. Local catalog population installed 48 reviewed built-ins alongside the four existing clones. Read-only running API/browser checks confirmed editable narrator profiles, saved speeds, friendly History labels and mobile/desktop layouts.
- The rollout preserved all 10 profile IDs/settings/timestamps except the intentionally removed model field, all 45 generations and their related tables, and all 2,539 audio/image/reference files. No profile or voice deletion was necessary. Private data backups and a post-migration database snapshot are retained outside Git.
- PR17 remains stacked on PR16 and non-draft. Its Git history was consolidated into enrollment tooling, catalog/storage/API, frontend workflow and documentation commits. The consolidated tree exactly matched the reviewed implementation before this delivery record was added; backup refs retain the previous history.
