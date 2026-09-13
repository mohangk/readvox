# System cloned voices — phase one

> Historical plan: the protected system-profile design below was superseded by the [unified voice catalog](../plans/2026-09-13-unified-voice-catalog.md). The backend maintains built-in and cloned voices; every profile is editable and deletable. Offline installation adds voices only.

> The next proposed simplification is specified in [Voice-owned models and catalog population](2026-09-13-voice-owned-models.md). It moves the model into each voice, filters by language and introduces an explicit Qwen population/update command; implementation is deferred.

## Outcome

Make the four listening-test selections available in the normal Generate selector as permanent system profiles. Reuse their existing cloud enrollments and exact reference recordings. Document how to produce, evaluate, and install further cloned voices.

Implementation authorized by the user's go-ahead on the phase-one outline. The saved system originals are protected, with **Save As** for personal variations; the following names and speeds are the accepted defaults.

| Selection | Display name | Default synthesis speed | Stable system key |
| --- | --- | --- | --- |
| 16 | Kai Narrator | 1.0 | `readvox-kai-v1` |
| 11 | Vivian Narrator | 1.1 | `readvox-vivian-v1` |
| 6 | Bellona Narrator | 1.25 | `readvox-bellona-v1` |
| 1 | Neil Narrator | 1.0 | `readvox-neil-v1` |

These display names were selected following the user's request for more useful long-term names. They distinguish the approved narration clones from their source presets. Speed remains a setting, and the stable key carries the voice revision. Existing cloud voice IDs remain unchanged. A personal profile may have a different name while using the same enrollment. A newly approved recording/enrollment gets a new key version; changing only a display name does not require paid enrollment.

All four use English, the enrolled `qwen3-tts-vc-realtime-2026-01-15` model, and empty instructions. Copy the successful cloned-track synthesis speed, rather than inferring it from a filename or changing audio playback speed. Preserve reference-generation speed and instructions separately as provenance. Equal numeric speeds across different models do not establish equal perceived pacing.

Authoritative source: the local manifest and reference files for run `20260913T043114Z-0f3d936a` under `src/tts_app/static/clone-lab-data/`. Check the run ID when reading `latest.json`; prefer that run's manifest once located. Account-specific IDs and recordings stay out of Git. An absent fallback flag means the provider did not report one; do not record that as a measured quality guarantee.

## User experience

- Generate keeps one named-voice selector and Edit. System entries have a small textual “System” designation and appear in the same selector as personal profiles.
- Keep the user's current selection. If an English selection is missing, prefer system Kai after installation; retain the existing Chinese fallback. These four voices are English-only until separately validated for other languages.
- The editor retains its top action row and profile selector immediately after it. On a system profile, Save and Delete are disabled with visible explanatory text: “System voice. Use Save As to keep your changes.” Save As and Cancel remain available.
- Settings and long preview text can be changed in the editor and previewed without altering the saved system profile. Save As creates a normal editable/deletable personal profile, reusing the enrolled voice. It does not enroll another cloud voice. Existing personal-profile Save behavior stays intact.
- Disable the instruction field for a model that cannot accept instructions, and submit empty instructions for that model. Preserve an unsaved instruction draft when switching back to an instruction-capable model in the same editor session; restore saved values when changing profiles.
- Present friendly voice labels. Raw cloud identifiers are implementation details, not names users must choose between.
- Preserve unsaved-change warnings, browser selection per language, Text/URL drafts, Image review state, originating Generate mode, and `/voice-sample` direct entry.

## Persistence and provisioning

SQLite stores an immutable registered voice definition, including the provider/model/voice binding, language, defaults, reference path and hash, and provenance. A nullable unique `voice_profiles.system_key` identifies the corresponding protected profile. Personal profiles leave it null; sharing a registered cloud voice does not make a personal profile a system profile.

Store exact reference bytes and the private source manifest under `data/voices/`, outside the preview cache, static assets, and generation-owned audio. Profile deletion, generation deletion, and preview-cache clearing never delete these assets or enrollments. System assets have no application deletion flow in this phase; backup/restore covers SQLite and the complete voices directory. Any eventual retirement requires a separate explicit operator action.

An offline install command validates and imports the existing approved experiment manifest. It performs no network requests. Installation is idempotent: identical input preserves profile IDs and timestamps; changed content for an existing system key is rejected. A materially different future voice gets a new key/version. Check all name conflicts before committing any records; report conflicts without renaming or overwriting personal profiles.

On startup, reconstruct a missing protected profile from its registered definition while preserving every existing profile ID. Never reseed deliberately deleted personal/default profiles. Normal API and storage update/delete operations cannot remove or alter a system original. Client payloads cannot assign system status.

“Always there” means installed system profiles remain present across normal app operations and restarts. A fresh installation must provision the private bundle for its provider account before these four can synthesize. Startup never enrolls, recreates, or checks a cloud voice. A provider failure remains an explicit generation/preview error; do not substitute another voice. Restoring a backup requires the matching provider account and region. Missing local reference bytes should produce an operator diagnostic and must not erase an otherwise usable registered cloud voice.

## Shared synthesis behavior

Build a shared capability view from the active provider's supported built-ins and that provider's registered voices. Accept only registered model/voice combinations for custom voices. The cloning model supports no instructions. Apply the registered voice's language restriction consistently to preview, profile save, and generation.

Text, URL, and OCR submissions continue to send a profile ID. Resolve it once before generation creation and snapshot profile ID/name, model, cloud voice ID, language, speed, and instructions. Each segment consumes this snapshot. Editing/deleting a personal derivative cannot alter an existing job. OCR language remains attached to its draft; an English system profile cannot silently change a Chinese draft.

Keep existing requests without profile IDs and existing built-in instruction profiles working. Keep the configured global instruction-model default: selecting a clone chooses its own model through its snapshot. No global switch to the cloning model is required.

Cache identity continues to include model, cloud voice, language, speed, instructions, and preview text. Profile name and system/personal status are not synthesis inputs. The same settings share cached audio; changing a synthesis input separates entries.

## Delivery boundaries

- Framework-free frontend; one FastAPI service and SQLite database.
- No changes to extraction, segmentation, playback stitching, or existing audio.
- No enrollment UI, automatic enrollment, retries, startup job recovery, voice design, or cloud deletion.
- No new generation-history schema or invented historical model metadata.
- One production PR based on named-profile functionality. PR #16 remains open as of planning; use a stacked branch based on `feat/named-voice-profiles` until it merges. Keep experimental pages out of this production diff.
- Preserve the existing experimental workflow at its pinned Git revision as a historical record. Promote the reusable reference/enrollment/comparison operations into maintained operator tooling before production integration; new work should not require checking out an experiment branch.

## Durable operator tooling extension

The user requested reusable tooling under `scripts/`. Provide one thin entry point, `scripts/voices.py`, backed by focused modules in `src/tts_app/voice_tools/`. Move the enrollment adapter into `providers/qwen_enrollment.py`, keeping network details inside the provider boundary. Use the existing normal Qwen streaming provider for reference and comparison synthesis. The connection-reuse A/B experiment remains experimental.

Expose separate commands for `candidates`, `enroll`, `compare`, `inspect`, and `install`. Candidate voices/speeds/text, selected reference path, display name/stable key, evaluation passages, and output directory are arguments. Enrollment must also work with a supplied valid WAV independently of the candidate generator. Comparison accepts an existing enrollment and never enrolls implicitly. Installation is offline. Display the number of planned paid operations during a read-only `--check` before a paid command is run.

Store new assets by default in `data/voice-workshop/<run-id>/`; installed assets remain in `data/voices/`. Use a versioned manifest with explicit per-entry settings, relative paths rooted at the manifest directory, reference hashes, enrollment metadata, and evaluation status. Paths must behave identically for copied manifests and direct run manifests. Retain sample number plus run ID for listening references; stable voice keys identify approved voices across runs. Preserve compatibility by importing the old approved run without new enrollment or audio synthesis.

The operator explicitly accepts an evaluated voice during `install`; do not infer acceptance from completed synthesis alone. Reference/enrollment provenance is immutable once enrolled. Resume checks input hashes/settings and reuses saved IDs and audio; mismatched inputs require a new run. If enrollment outcome is uncertain, read-only provider lookup and explicit adoption of a matching returned ID are required before continuing. No automatic retry or reenrollment.

Generate a self-contained local listening report with relative audio links for each comparison. It works without the production app or static-data pointers; serve its selected output directory locally when needed. Keep private artifacts out of Git and packaged web assets. Add deterministic tests for CLI arguments, manifest migration, path handling, interrupted work, fake enrollment/synthesis, and installation boundaries.

## Acceptance

All four approved voices appear after provisioning, survive restart, and reject modification/deletion through both API and storage. Personal Save As copies remain editable/deletable. Preview and all three generation paths honor the chosen model, voice, speed, language, and empty clone instructions. Old profiles, history, audio, and drafts remain intact. Cache clearing retains references and profiles. Deterministic tests and desktop/mobile keyboard checks pass, followed by one short live generation using one installed clone in temporary storage. Listening across ordinary production segments is the user's final quality check; improved experimental consistency is not a promise of identical delivery at every boundary.
