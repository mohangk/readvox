# Durable Voice Tooling Implementation Plan

> Historical plan: the protected system-profile design below was superseded by the [unified voice catalog](2026-09-13-unified-voice-catalog.md). The backend maintains built-in and cloned voices; every profile is editable and deletable. Offline installation adds voices only.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the successful reference/enrollment/comparison workflow into reusable operator commands without requiring edits to experimental code.

**Architecture:** A thin `scripts/voices.py` entry point delegates to tested `tts_app.voice_tools` modules. Enrollment HTTP stays in a provider adapter; synthesis reuses `QwenTTSProvider`. Private versioned run artifacts are separate from installed system-profile assets and production history.

**Tech Stack:** Existing Python, argparse, pathlib, httpx, Qwen provider, pytest, and simple generated HTML; no new framework.

**Spec:** [System voice design, including durable tooling extension](../specs/2026-09-13-system-cloned-voices.md).

## Global Constraints

- Framework-free frontend; one FastAPI service and SQLite database.
- No changes to extraction, segmentation, playback stitching, or existing audio.
- No enrollment UI, automatic enrollment, retries, startup job recovery, voice design, or cloud deletion.
- No new generation-history schema or invented historical model metadata.
- Explicit operator enrollment commands may call the provider; app startup, inspection, comparison, and installation never enroll voices implicitly.
- Existing approved cloud IDs and original reference bytes are retained.
- No credentials, cloud enrollment manifests, references, or generated audio are committed.
- This document describes proposed tooling; none of these new commands exists yet.

## Proposed command surface

Commands run from the repository root using its existing virtual environment:

```bash
.venv/bin/python scripts/voices.py candidates --text reference.txt --voices Kai Vivian Bellona Neil --speeds 1 1.1 1.25 --output data/voice-workshop/candidates --check
.venv/bin/python scripts/voices.py candidates --text reference.txt --voices Kai Vivian Bellona Neil --speeds 1 1.1 1.25 --output data/voice-workshop/candidates
.venv/bin/python scripts/voices.py enroll --reference selected.wav --name "Kai Narrator" --key readvox-kai-v2 --model qwen3-tts-vc-realtime-2026-01-15 --speed 1 --output data/voice-workshop/kai-v2
.venv/bin/python scripts/voices.py compare --manifest data/voice-workshop/kai-v2/manifest.json --passages passages/ --speeds 1 1.1 1.25
.venv/bin/python scripts/voices.py inspect --manifest data/voice-workshop/kai-v2/manifest.json
```

`--check` is available for all mutating commands, validates inputs and reports intended enrollments/TTS requests without making calls or writing files. `passages/` contains ordered UTF-8 `.txt` files; each file is a separate synthesis request. `--output` selects a new run directory and refuses accidental reuse. `--resume <manifest>` explicitly continues an existing run after checking input identity. The example uses a new v2 key because the approved v1 already exists; do not reenroll v1 to assign its display name.

After the main plan's storage/installer tasks land, expose:

```bash
.venv/bin/python scripts/voices.py install --manifest data/voice-workshop/kai-v2/manifest.json --accept readvox-kai-v2 --speed 1 --check
.venv/bin/python scripts/voices.py install --manifest data/voice-workshop/kai-v2/manifest.json --accept readvox-kai-v2 --speed 1
```

`install` requires a completed comparison and a tested selected speed. It records explicit operator acceptance before calling the offline installer. Importing the four historical selections records their already established acceptance rather than requiring another comparison.

## Task A: Stable manifests and provider boundary

**Files:** Create `src/tts_app/voice_tools/__init__.py`, `src/tts_app/voice_tools/manifest.py`, `src/tts_app/voice_tools/audio.py`, `src/tts_app/providers/qwen_enrollment.py`, `tests/test_voice_tool_manifests.py`, `tests/test_qwen_enrollment.py`.

**Interfaces:** `load_manifest(path: Path) -> dict`, `save_manifest(path: Path, manifest: dict) -> None`, `resolve_asset(manifest_path: Path, relative_path: str) -> Path`; retain `QwenEnrollment.create(path, name)` behavior in the new provider location. Audio helpers own WAV writing/hashing and measured boundaries, extracted from the experiment without importing it.

- [ ] Write failing tests for version rejection, relative-path resolution, path escape rejection, checksum verification, atomic manifest replacement, and mocked enrollment success/error/model mismatch.
- [ ] Use schema version 1 with a single run root and explicit records:

```json
{
  "schema_version": 1,
  "run_id": "example-run",
  "kind": "voice",
  "voices": [{
    "key": "readvox-kai-v2",
    "name": "Kai Narrator",
    "language": "en",
    "speed": 1.0,
    "reference": {"path": "reference.wav", "sha256": "example-hash", "provenance": {}},
    "enrollment": null,
    "comparisons": [],
    "acceptance": null
  }]
}
```

The code schema validates actual SHA-256 values, model/voice constraints and provenance; the strings above illustrate structure. A `kind='candidates'` run instead has `samples` with number, per-sample synthesis settings, text hash, relative audio path and status. Enrollment stores voice ID, exact target model, preferred name, endpoint region, request ID and reported fallback fields. Comparisons store passage hash/text path, settings, individual audio paths, status and measured boundaries. Acceptance stores key, tested speed and timestamp. Do not infer per-voice settings from a shared defaults object.
- [ ] Preserve the proven audio-only enrollment payload; generate future preferred names from a readable short key plus uniqueness suffix within the provider's supported length. Keep existing IDs unchanged. Before an external create, persist an `enrolling` state and preferred name; save the response before any synthesis. Mark uncertain outcomes for operator lookup, never automatic retry.
- [ ] Add a read-only lookup helper to the enrollment adapter and an explicit adoption path that validates voice ID, target model and account/region before persisting recovered enrollment. Do not expose cloud deletion.
- [ ] Run `.venv/bin/pytest tests/test_voice_tool_manifests.py tests/test_qwen_enrollment.py -q`, review boundaries/data ownership, and commit `refactor: establish durable voice artifacts and enrollment adapter`.

## Task B: Reusable candidate, enrollment, and comparison commands

**Files:** Create `scripts/voices.py`, `src/tts_app/voice_tools/cli.py`, `src/tts_app/voice_tools/candidates.py`, `src/tts_app/voice_tools/enroll.py`, `src/tts_app/voice_tools/compare.py`, `src/tts_app/voice_tools/report.py`, `tests/test_voice_tools.py`.

**Interfaces:** `cli.main(argv: list[str] | None = None) -> int`; each command accepts parsed inputs and injected provider dependencies. `scripts/voices.py` only calls `main()`. Import production synthesis/provider types, never the session-lab adapter.

- [ ] Add failing CLI/fake-provider tests for arbitrary voice/speed lists, supplied reference WAV, one or many evaluation passages, request counts, dry run, invalid settings before paid calls, explicit resume and uncertain enrollment recovery.
- [ ] Implement argument-driven reference generation with configurable model, language, instructions file, voices, speeds and text. Default reference model to the instruction model and include the guide's audiobook instructions explicitly in the manifest. Remove dependencies on latest History, six paragraphs, static latest pointers and hardcoded counts.
- [ ] Implement standalone enrollment for a validated supplied WAV. When it came from a candidate run, accept its manifest and sample number to retain complete provenance and verify exact byte identity. When supplied independently, record only metadata actually supplied; do not invent source preset or instruction metadata.
- [ ] Implement comparison with an existing enrollment and separate passage requests through `stream_speech`. Clones send empty instructions. Support an optional original-control candidate manifest/sample; preserve that candidate's full settings and label the two configurations accurately. Do not require an original control for a supplied external recording.
- [ ] Produce `report.html` with relative reference/comparison audio links, sample/run identity, escaped labels and error messages, measured joins, and explicit incomplete/failed states. It uses no production API. Test escaping, accessible controls, audio links and unavailable partial tracks. Document local serving via `python -m http.server --bind 127.0.0.1 --directory <run-directory>`.
- [ ] Implement `inspect` as a local metadata/status summary; add `enroll --lookup` and `enroll --adopt-voice-id` for the explicit recovery flow. Only the adoption operation updates the local manifest. Provider lookup is opt-in; inspect never checks cloud state silently.
- [ ] Run `.venv/bin/pytest tests/test_voice_tools.py tests/test_voice_tool_manifests.py tests/test_qwen_enrollment.py -q`; inspect generated reports at desktop/mobile widths using fake data; review and commit `feat: add reusable voice workshop commands`.

## Task C: Historical import, installation handoff, and documentation

**Files:** Create `src/tts_app/voice_tools/legacy_import.py`, `tests/test_voice_tool_import.py`; update `src/tts_app/voice_catalog_install.py` when created by the main plan, `src/tts_app/voice_tools/cli.py`, `docs/cloned-voices.md`, `docs/operations.md` and applicable documentation tests.

**Interfaces:** `import_legacy_comparison(source: Path, output: Path) -> Path` produces a version-1 manifest by copying exact references and comparison assets. `install` adapts accepted version-1 records into `RegisteredVoiceDefinition` and delegates to the main plan's offline installer/storage boundary.

- [ ] Test importing the four selections with synthetic legacy fixtures, preserving IDs/model/speeds, original source settings, audio hashes, comparison boundaries and reported fallback information. Verify no external calls and no mutation of the original run.
- [ ] Add `import-legacy --manifest <source> --output <new-run-directory>`. Resolve old root-relative references using their documented layout, then write new paths relative to the new manifest. Copy all referenced bytes; do not regenerate comparisons. Current names remain provenance; proposed Narrator names become editable local labels until installation.
- [ ] After the main plan's Tasks 1 and 2, implement `install --accept <key> --speed <tested-speed>`, preserving protections, atomicity and idempotence. Test existing-key conflicts, untested speeds, incomplete evaluation, and ordinary profiles sharing an installed voice. Legacy approval applies only to the exact recorded four voices and speeds.
- [ ] Replace future-use instructions in the cloning guide with maintained commands. Retain the original commands/settings as historical explanation. Document manifests, account/region binding, naming/version policy, backups, optional local report serving, explicit paid operations and interruption recovery.
- [ ] Run the repository's full Python and JavaScript checks and `git diff --check`, followed by architecture review. Use the main plan's single saved-clone generation canary for synthesis acceptance. Do not create an extra paid enrollment merely to verify this refactor; the adapter's transport is covered by mocks and the existing successful enrollments. Record that new enrollment is not live-retested.
- [ ] Commit `feat: preserve legacy clones and connect durable voice tooling`; keep this work independently reviewable before the system-profile UI integration.

## Delivery order and review

Implement Tasks A/B and the offline legacy conversion first. Implement storage and offline installation from the main plan next, then complete Task C's installation wiring. Continue with the main plan's shared validation and frontend tasks. This order avoids a circular dependency and yields tooling that can be reviewed separately from UI changes.

Review checks: production imports no experiment modules; the entry script contains no provider protocol or persistence logic; references have explicit manifest ownership and no automatic cleanup; candidate text is independent of History; enroll/compare/install are distinct operations; names, stable keys, provider IDs and speed settings remain separate; all old references/enrollments survive unchanged.
