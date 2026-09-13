# Voice-owned models and catalog population

Status: implemented and verified; loaded locally through autoreload and delivered in PR17 with four logical commits.

This supersedes the profile-owned model and multiple-model catalog design recorded in the [delivered unified catalog plan](../plans/2026-09-13-unified-voice-catalog.md). The [implementation plan](../plans/2026-09-13-voice-owned-models.md) records the implementation and verification.

## Outcome

A person edits a named reading profile by choosing a language and a base voice, then adjusting speed, instructions where supported, and preview text. Models are backend configuration. Simplify the persistence and request paths along with the UI: remove multiple-model catalog structures, profile model storage, model controls, and model-change state.

Provide a maintained script that populates an empty catalog and updates an existing one from reviewed Qwen definitions. Adding a provider later should require a provider-specific source and small command dispatch change; implementing additional providers or a discovery framework is outside this phase.

## Data ownership

| Record | Owned values |
| --- | --- |
| Catalog voice | Stable local ID/key, provider, provider voice ID, friendly name, built-in/cloned kind, one synthesis model, supported languages, instruction capability, availability, optional private provenance, timestamps |
| Named profile | ID/name, `voice_id`, language, speed, instructions, preview text, timestamps |
| Generation | Resolved provider/model/raw voice and friendly names plus profile ID/name and reading settings, captured before the job begins |

Keep the existing uniqueness boundary `(provider, provider_voice_id)`. A multilingual voice has one catalog record, for example `languages: ["en", "zh"]`, and appears once in either filtered list. Language is not part of voice identity. A model version change updates the backend binding; it does not create another selectable copy of the same provider voice.

Replace `voices.models_json` with `model TEXT`, `languages_json TEXT`, and `supports_instructions INTEGER`. Keep the existing identity, availability, provenance and timestamp fields. Remove `voice_profiles.model`; profiles reference only `voice_id` for synthesis identity. There is no preferred-model field, compatibility matrix or per-profile model override in the final runtime.

Catalog model changes affect subsequent previews and generations. A running job uses its original resolved snapshot for every segment. Historical generations and cached audio keep the settings actually recorded; do not infer missing historical metadata.

## Qwen definitions and model binding

Use one checked-in Qwen catalog source, `src/tts_app/providers/qwen_catalog.py`, with friendly names, a single model and explicit supported app languages per voice. Shared constants can avoid repeating model strings, but each emitted definition is complete. Remove duplicated English/Chinese voice inventories and the runtime multi-model catalog projection. Existing provider protocol and operator experiment inputs can still carry an explicit model: the simplification concerns catalog/profile selection, not the underlying synthesis API.

Proposed initial bindings use the existing supported model families: `qwen3-tts-instruct-flash-realtime` for documented instruction-capable presets and `qwen3-tts-flash-realtime` for documented presets that require that family. Record the chosen model directly in each definition, rather than choosing it at request time. The four existing clones retain their enrollment's exact `qwen3-tts-vc-realtime-2026-01-15` model, English support and disabled instructions. Do not move an enrolled clone to another model by inference. This phase does not adopt newer provider protocol families.

Review built-in definitions against the official [Qwen-TTS voice list](https://www.alibabacloud.com/help/en/model-studio/qwen-tts-voice-list), which publishes supported languages and models per preset. Record the source URL and review date with the checked-in source. Only publish the supported Readvox languages `en` and `zh`; a voice appearing in both filters remains one row. Descriptive accent labels alone do not establish or limit language support. Source inspected on 2026-09-13; verify it again when implementing or refreshing definitions.

## Population and refresh command

Add a thin script using this checkout's source path:

```bash
.venv/bin/python scripts/populate_voice_catalog.py --provider qwen --check
.venv/bin/python scripts/populate_voice_catalog.py --provider qwen
.venv/bin/python scripts/populate_voice_catalog.py --provider qwen --data-dir /tmp/readvox-catalog-demo
```

The default target follows the existing application settings. `--data-dir` selects an isolated target and derives its database path from that directory. Show the resolved target in the command report. `qwen` is the only production provider accepted in this phase. The command must not require provider credentials: it installs reviewed definitions locally and makes no enrollment, synthesis or lookup request.

`--check` validates the complete input, inspects an existing database without source-file changes using an exclusive SQLite-compatible lock and recovery in a private copy, and reports additions, updates, unchanged entries and retirements without creating a directory/database or running a durable migration. If a schema upgrade is needed, include that in the report. On the current POSIX deployment, fail clearly if open connections or transactions prevent a consistent snapshot; do not copy a changing database/WAL pair. The explicit population provider establishes legacy raw-profile ownership, and invalid provider configuration must fail before target access. On apply, initialize or migrate the schema and synchronize the selected provider's built-in catalog in one transaction. Reject malformed definitions, duplicate identities and collisions with installed clones before committing anything. Identical re-runs preserve IDs and timestamps.

Sync inserts new presets, updates changed names/model/languages/capabilities, and marks built-ins absent from the complete reviewed source unavailable. It preserves the IDs of retained or returning voices. An empty or invalid source is an error, not permission to retire every voice. It never changes profiles, generations, reference assets, installed clones or another provider's catalog entries. Report changed model bindings because they affect future speech.

Updating available Qwen presets is a two-step operator workflow: review/update the checked-in definitions from the official voice list, then run this command. Running an unchanged source does not discover newly published voices automatically. Do not add website scraping or assume a public preset-discovery API. Qwen's [customization list operation](https://www.alibabacloud.com/help/en/model-studio/voice-clone-design-http-api) is used by the existing enrollment workflow; it is not the population source for built-in presets.

Keep clone installation in `scripts/voices.py install`: it imports an existing accepted private bundle into the same simplified catalog. From empty storage, run the population command for built-ins, then optionally install the saved clone bundle. Catalog population and clone installation create no profiles and do not enroll new cloud voices. The application retains its ordinary one-time default-profile seeding once compatible catalog voices exist; deliberately deleted profiles are never recreated.

Make explicit population/sync the owner of built-in updates. Remove unconditional catalog synchronization from app startup. The app reads SQLite for voice options and synthesis resolution, so a successful catalog refresh is visible on the next options request/new job. An empty catalog produces a clear empty state with Preview/Save/generation unavailable; operational setup documentation explains the population command. Startup must remain able to serve the empty app without provider calls or invalid default profiles.

## Editor and API

Keep Save, Save As, Cancel and the profile selector in their existing top positions. In the settings area, place Language before Base voice and remove the model control entirely. Base voice options include a friendly provider label, for example `Kai Narrator · Qwen · Cloned`. Filtering uses `voice.languages`, availability and the active provider. Multilingual voices are not duplicated.

Keep a compatible selection when switching languages. If it becomes incompatible, clear the selection and require the user to choose an available voice; do not silently substitute one. Show a useful empty state when a language has no compatible voices. A saved retired voice is shown as unavailable until replaced. Capability text and instruction availability come directly from the selected voice. Remove per-model instruction maps and model-change handlers; retain ordinary unsaved-form and cancel behavior.

New profile and preview requests use `voice_id`, language, speed, instructions and text, with no model field. Profiles expose no model, including derived model aliases. `GET /api/voices` and editor options expose one model and flat language/instruction capabilities per voice; private provenance remains excluded. The UI does not need to display the technical model.

Use one resolver for profile validation, preview and profile-based generation. It validates provider/availability, language, speed and instruction support, then resolves the voice's exact model and provider identity. Preview cache identity includes resolved model, provider identity, language, speed, instructions and text, never a profile name. A model binding change must not return cached speech from the prior model.

Keep necessary legacy HTTP input translation at a small request boundary. A legacy raw voice resolves within the active provider; an accompanying model can only match the catalog binding and cannot override it. Reject conflicts clearly. Preserve the existing no-profile generation contract with explicit voice/speed/language and the configured model; it remains separate from named-profile editing. Avoid keeping the obsolete model-selection options response or a multi-model internal graph solely for the old editor.

OCR recognition language remains attached to its draft. Editing a voice profile must not change that draft or its language. Text, URL and OCR generation each resolve the selected compatible profile once before creating the job.

## Migration and authorized cleanup

The user explicitly permits deletion of incompatible old data rather than retaining complexity to support it. First inventory and report the actual incompatibilities on a private database copy. Migrate compatible voice/profile IDs, names, reading settings and timestamps; remove the obsolete columns in a one-time migration. A valid profile can adopt its voice's selected catalog model because the model no longer belongs to the profile. Report that binding change rather than pretending the old model was preserved.

If a profile's identity cannot be resolved, language is unsupported or its instructions conflict with the final voice capability, it may be deleted under this authorization. Remove unusable legacy catalog records only after handling their profile references. Use a transactional migration with a deterministic cleanup report listing local record IDs and reasons. Do not build a permanent compatibility table, recovery-profile mechanism or additional selector to retain incompatible records.

The cleanup is scoped to records incompatible with the new voice/profile structure. Existing independent generation snapshots, audio, images and reusable enrollment/reference bundles do not require deletion for this schema change. Routine future catalog sync only marks retired presets unavailable; it is not a recurring profile-cleanup command. Back up before rollout and check that no generation is active before triggering the schema migration through the running app's autoreload.

## Acceptance

- The final schema stores exactly one model per voice and none per profile; the editor has no model selector or model-change state.
- A bilingual provider voice remains one record, selectable once under English and once under Chinese. English-only clones disappear from the Chinese choices.
- Population works from absent/empty storage without credentials; repeat runs are no-ops; refreshed definitions add/update/retire only the selected provider's built-ins and preserve stable IDs.
- `--check` changes no files; invalid, empty or colliding sources leave the database unchanged. Neither population nor startup enrolls or synthesizes.
- Profiles and unsaved preview use the catalog binding. Model changes separate preview cache entries; active jobs retain the original snapshot. All three generation input paths are covered.
- Ordinary Save/Save As/Delete, persisted selection, missing selection, navigation drafts and OCR language behavior remain functional.
- Migration tests cover compatible records and authorized incompatible-record cleanup, transaction rollback and unchanged independent generation/media data.
- Run deterministic Python/JS checks, mobile/desktop and keyboard browser checks, one saved-profile live Qwen canary in temporary storage, and architecture review before implementation completion.
- Update schema, configuration, cloning and setup documentation during implementation. Update PR17 and retain ready-for-review status only after implementation is verified; the current planning turn makes no running-app change.
