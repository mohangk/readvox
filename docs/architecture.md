# Readvox Architecture

Readvox is a local-first FastAPI app for turning text, URLs, reviewed drafts, and future input sources into streamed text-to-speech audio. It should stay small enough to run as one localhost service, but its internals should be split by responsibility so new workflows do not turn into one large route file, one storage method pile, or one monolithic JavaScript file.

## Core Principles

- Keep the app local-first: one FastAPI process, one SQLite database, one data directory, and optional private HTTPS proxy access for trusted devices.
- Keep external paid services behind provider interfaces with deterministic fake providers for tests and local UI checks.
- Treat stored user data as durable. Do not remove stored images, generated audio, cached smoke-test artifacts, or local data files unless the user explicitly asks or an app deletion flow is being exercised.
- Preserve the behavior distinction between client state and backend persistence. Clearing frontend state must not imply deleting backend data unless the user invokes a deletion flow.
- Prefer focused vertical slices: provider/config, storage, route/API, frontend state/UI, then docs and tests.
- Add tests at the layer that owns the behavior. Storage tests cover persistence and cleanup; API tests cover contracts and failure status; frontend static tests cover DOM wiring and browser state transitions.

## Runtime Shape

FastAPI serves both the API and static frontend. The default deployment binds plain HTTP to `127.0.0.1:8001`; remote access belongs behind a private HTTPS proxy.

Durable data is split between SQLite and the filesystem:

- SQLite stores generations, text segments, audio segment metadata, provider settings, playback progress, workflow drafts, and source-asset metadata.
- Audio files are cached under `data/audio/<generation_id>/`.
- OCR images are stored under `data/images/<ocr_draft_id>/<ocr_draft_image_id>/`.

The database owns metadata relationships. The filesystem owns byte storage. Any feature that creates filesystem data must define its ownership and cleanup semantics and test them. Catalog voice references and operator workshop runs are deliberately retained: preview-cache, profile and History deletion do not own these assets.

## Backend Boundaries

`src/tts_app/api.py` should remain the app factory and shared top-level routes. Feature-specific route groups belong under `src/tts_app/routes/` once they have more than trivial behavior. Shared route helpers, such as generation scheduling, belong in small helper modules rather than being copied between route files.

Provider-specific behavior belongs behind interfaces:

- TTS providers live under `src/tts_app/providers/`.
- OCR providers live under `src/tts_app/ocr_providers/`.
- Fake providers must remain deterministic and should be the default for tests.
- Qwen credentials come from `DASHSCOPE_API_KEY` or `QWEN_API_KEY`.

Generation logic should call provider interfaces, not provider implementations. Route handlers should create validated requests and delegate durable work to storage and generation services.

## Storage And Migrations

`src/tts_app/storage.py` owns schema creation, one-time migrations, and persistence operations. Schema changes should be forward migrations that move existing data into the new shape and then remove obsolete schema paths. Do not leave long-lived runtime branches for old schemas after the migration is complete.

Storage methods should expose behavior-level operations, not raw table manipulation. Examples:

- create a generation with text segments
- record an audio segment
- create or append workflow draft source assets
- rebuild a draft's reviewed source text from child assets when appropriate
- link a workflow draft to a generation
- delete unlinked drafts
- force-delete linked drafts during generation deletion

As workflows grow, split storage internals into helper modules or mixins while preserving the public `Storage` API used by routes and tests. Workflow-specific storage tests, such as `tests/test_ocr_storage.py`, are the acceptance surface for storage splits.

## Drafts And Linked Artifacts

Some workflows need intermediate user review before they become a durable audio generation. Model those workflows as drafts that are separate from generations until the user explicitly creates audio. This separation is intentional:

- A draft is a reviewable source document assembled from one or more user-provided or provider-derived assets.
- The draft stores editable reviewed text that becomes the source of truth for audio generation.
- Child asset rows preserve raw provider output, source file metadata, retry state, and diagnostics.
- Creating audio stores the reviewed text as generation `full_text`, records workflow-specific settings, and links the draft to the generation.

Linked drafts should disappear from active draft-picking surfaces because their user-facing recovery path is History. They should not be deleted by frontend state reset. Linked draft and stored source-asset cleanup belongs to generation deletion from History.

OCR is the current example of this model:

- OCR drafts are assembled from ordered source images.
- `ocr_drafts.combined_text` is the reviewed source of truth for audio generation.
- `ocr_draft_images.extracted_text` preserves raw per-image OCR output for retry, delete, and diagnostics.
- Creating image audio sets `source_type = image` and links the draft to the generation.
- For Chinese OCR, preserve only visible Chinese text and visible pinyin. Do not generate missing pinyin, transliterate Chinese characters into pinyin, translate, summarize, or infer text that is not visible in the image.

## Frontend Direction

The frontend should stay framework-free, mobile-first, and plain JavaScript, but it should not grow as one giant `app.js`. New work should continue moving code into feature modules with explicit imports and narrow responsibilities.

Current module direction:

- `app.js`: app bootstrap, top-level navigation, shared generation/playback orchestration.
- `history.js`: History rendering, search, deletion, and open actions delegated to app playback; failed status and escaped stored diagnostics leave partial audio accessible.
- `dom.js`: DOM element lookups.
- `state.js`: shared browser state.
- `utils.js`: small reusable helpers such as escaping and busy-button handling.
- `ocr.js`: Image OCR and Draft Images workflow.

Future modularization should split `app.js` further when touching related behavior:

- `playback.js`: audio queue, segment playback, progress persistence, autoplay/manual playback, scroll-follow.
- `generation-form.js`: Text/URL/Image mode switching, form payload creation, and submit state.
- `voice-controls.js`: language, voice, speed, preference, and sample playback behavior.
- `api-client.js`: small fetch helpers for JSON, 204 responses, errors, and button-wrapped actions.

Do this incrementally. Do not pause feature work for a large frontend rewrite. When a change touches a coherent area in `app.js`, extract that area with focused static tests and keep public behavior unchanged.

Frontend state rules:

- UI reset helpers should clear local state and DOM affordances only.
- Backend deletion must go through explicit API calls and confirmation where user data is removed.
- Busy-button helpers must leave controls in the correct final enabled/disabled state after async wrappers restore button state.
- Browser asset version query strings should change when HTML/CSS/JS compatibility changes.
- SQLite-backed playback telemetry should stay local-first and content-free. Store diagnostic generation playback events in SQLite, delete them with the generation, and do not collect article text, OCR text, extracted URL content, generated audio bytes, or provider raw responses.

## Testing Approach

Use deterministic tests by default. Paid provider calls do not belong in normal test runs. Before marking an implementation feature complete, run the opt-in live provider integration canary once to verify the Readvox API-to-provider boundary with one short sample and one supported voice.

Run before claiming work is complete:

```bash
.venv/bin/pytest -q
npm run check:js
npm run lint:js
npm run test:js
```

Run the live canary with local credentials after the deterministic suite passes:

```bash
set -a
source .envrc.local
set +a
RUN_QWEN_INTEGRATION=1 .venv/bin/pytest -m live_provider -q
```

The live canary should remain deliberately narrow: one Text generation API request using a saved profile, one documented model/voice combination, a temporary database/data directory, and a non-empty audio assertion. It normally uses an instruction profile. With `QWEN_LIVE_CLONE_MANIFEST` set to the absolute path of an accepted version-1 workshop manifest containing `readvox-kai-v1`, it instead installs the Kai Narrator catalog voice in temporary storage, creates a personal profile through the API, and reuses that enrollment for the same single paid synthesis request. It never creates an enrollment or modifies production History. Deterministic tests verify that preview sampling does not create a History entry. It is an integration health check, not an exhaustive provider voice test.

Prefer focused tests first:

- storage changes: `tests/test_storage.py` or `tests/test_ocr_storage.py`
- API changes: route-specific API tests
- provider behavior: fake and provider contract tests
- frontend wiring: `tests/test_frontend_static.py`
- docs/setup changes: `tests/test_docs.py`

Then run the full verification set.

## Future Feature Pattern

For new workflows, use this order unless there is a concrete reason not to:

1. Configuration and provider boundary, with a fake implementation.
2. Storage schema and migration, with cleanup semantics.
3. API routes and shared route helpers.
4. Frontend module and state transitions.
5. Documentation and setup examples.
6. Full verification and a logical commit series.

Commit history should tell the same story as the architecture: tooling/config, provider boundary, storage, API, frontend, then documentation cleanup when needed. Fold review-fix commits into the relevant layer before merging when practical.

## Architecture Review

After every non-trivial change, run an architecture review against this document before merging or pushing to `main`. The review should look for boundary drift, accidental data-loss paths, provider calls leaking outside adapters, frontend monolith growth, missing focused tests, and commit history that hides architectural decisions.

Use `docs/architecture-review-subagent.md` as the review prompt. Treat findings as code review comments: fix high-risk issues before merge, document intentional exceptions, and keep the review focused on project architecture rather than style preferences.

## Voice Catalog And Named Profiles

`voice_storage.py` owns the backend-managed SQLite catalog. A voice stores one provider/model binding, a friendly name, built-in/cloned kind, availability, supported languages and instruction capability, plus optional private provenance. `(provider, provider_voice_id)` identifies a voice once: bilingual voices have `languages=["en","zh"]`, not separate records per language. `voice_profiles` references `voice_id` and owns name, language, speed, instructions and preview text. Profiles have no model field. Every profile is editable and deletable; deletion never owns the catalog voice, enrollment, references or History.

`providers/qwen_catalog.py` is the reviewed source of built-in Qwen definitions. `scripts/populate_voice_catalog.py` delegates to `voice_catalog_sync.py` for explicit, offline population and refresh. It requires no provider credentials, creates absent storage, preserves stable IDs/no-op timestamps, and marks missing presets unavailable. `--check` reports work without changing the target. Only the selected provider's built-ins are synchronized; clones and profiles are independent. New provider support requires its adapter/source and configuration, not merely a database name. The Qwen source must be reviewed and updated before the command can introduce newly published voices.

Startup initializes schemas and reads the catalog; it does not overwrite catalog bindings from provider lists or perform provider discovery. Empty storage serves an empty editor until explicitly populated. Ordinary default profiles are seeded once when compatible voices exist; deleted profiles never reappear. `providers/options.py` derives workshop validation capabilities from the reviewed catalog source.

`voice_catalog.py` resolves catalog identity, active provider, availability, language and instructions once for profile validation, preview and profile-based generation. `synthesis.py` owns request limits/language mapping and a small legacy HTTP model input that may only match the catalog binding. New editor requests send `voice_id` and reading settings without model. Profile responses also contain no model. `routes/voice_profiles.py` delegates persistence; catalog HTTP access is read-only and excludes private provenance. Editor options read current SQLite state on every request.

`generation_settings.py` captures provider, model, raw voice, friendly voice/profile names and reading settings before creating a generation or mutating an OCR draft. Every segment uses that snapshot, even after profile deletion or catalog model updates. Legacy generation requests without `profile_id` retain explicit voice/speed/language, configured model and empty instructions. No missing historical model is invented. Preview cache identity includes the resolved model and all synthesis inputs, so model updates cannot reuse audio from the old model.

`profile-selection.js` manages compact profile selection/browser persistence. `profile-editor.js` owns Save, Save As, Delete and unsaved changes. `instruction-voice-sample.js` filters base voices by language, displays provider labels, and applies each voice's instruction capability. It has no model selector or per-model draft bookkeeping. An incompatible language change requires another voice selection. `app.js` orchestrates views while preserving Text/URL/Image drafts; OCR recognition language stays tied to its draft.

## Voice Installation And Operator Tooling

`voice_catalog_install.py` is an explicit offline boundary. It verifies accepted source metadata, reference checksums, comparison settings and conflicts before copying durable bundles under `data/voices/` and installing catalog entries in one SQLite transaction. `voice_installation.py` validates the installation definitions. Installation never enrolls, synthesizes or writes profiles. Matching installs are idempotent; conflicting keys, provider identities or changed bundles are rejected. Accepted reference/evaluation speeds remain manifest provenance, not active catalog profile defaults. Filesystem publication precedes database installation, so failed registration retains recoverable bundles rather than deleting data. Back up SQLite, installed bundles and complete private source/workshop runs together.

`scripts/voices.py` resolves its checkout and delegates to `voice_tools/cli.py`. The `voice_tools` package owns versioned manifests, rooted/checksummed assets, reference generation, explicit enrollment workflows, independent comparison requests, local reports and offline catalog installation. These operator-owned runs are outside production History and have no automatic cleanup. Installation accepts only version-1 workshop manifests with accepted, completed comparisons. Comparison manifests validate complete settings, identities, safe IDs, passage states and measured completion metadata before side effects. The complete requested matrix is saved before synthesis so interruption can resume without repeating completed passages.

Provider protocol stays in `providers/qwen_enrollment.py` (audio-only HTTPS create and explicit read-only list) and `providers/qwen.py` (WebSocket speech). No production module imports experimental runners. Before create, tooling persists `enrolling` and a preferred name; uncertain results require operator lookup/adoption, never automatic create retries. Credential fingerprints identify keys rather than permanent accounts, and recovery verifies region/model/account lookup with explicit acknowledgement after key rotation. Inspection, installation, startup and ordinary synthesis do not silently enroll or list cloud voices. SQLite is authoritative for installed catalog entries; startup does not scan reference directories or import arbitrary manifests.

## Background Generation And Recovery

`generation_jobs.py` owns asyncio tasks for the single FastAPI process. Submission durably claims a generation and registers its task before returning; HTTP request completion, tab closure and EventSource disconnection do not own task cancellation. `routes/shared.py` schedules Text, URL and reviewed OCR through the same runner. Run exactly one process against a data directory. Lifespan startup marks abandoned queued/running jobs failed with an interruption reason, without paid calls; shutdown cancels owned jobs and records interruption. Deletion holds a generation guard, cancels and awaits its task, then removes its stored assets.

`generation_storage.py` owns transactional claims and checkpoints through a Storage mixin. `generation.py` publishes segment files by temporary write/flush/fsync/atomic rename, then commits text completion and audio metadata together. A file left before metadata commit belongs to unfinished work and may be replaced on Resume. Completed checkpoints are checked for a completed metadata row, existing nonempty file and matching byte count; inconsistent checkpoints stop recovery rather than overwrite completed audio. Continuous audio remains a rebuildable concatenation of completed segments.

`routes/generation_recovery.py` exposes manual Resume and eligibility. Resume retains the generation ID, source text, segment boundaries, synthesis snapshot and listening position. It never refetches a URL or resolves a mutable profile/catalog entry. Old generations without a complete model/voice/language/speed snapshot require a new generation; no model is guessed. There are no automatic retries or automatic startup resubmissions.

History API counts `completed_segments`/`total_segments` describe synthesis, separately from playback `progress_percent`. `history.js` owns the Resume action. `generation-updates.js` observes jobs with EventSource reconnection plus a five-second persisted-state refresh while active; stopping observation never stops generation. Reopening an active entry reconnects automatically. Provider connection/setup, audio inactivity, whole-segment and close waits are bounded inside the Qwen adapter; diagnostics retain stage and available provider IDs without including free-form provider messages, submitted text or credentials.
