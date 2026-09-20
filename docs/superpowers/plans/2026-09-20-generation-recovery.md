# Generation Recovery Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement these tasks in order with tests first.

**Goal:** Make generation independent of browser lifetime and safely resumable after failures or server interruption.
**Architecture:** Preserve provider boundaries and SQLite snapshots. Add a single-process job owner, atomic segment checkpoints, recovery routes and History actions.
**Tech Stack:** Python asyncio, FastAPI, SQLite, framework-free JavaScript, pytest, Vitest.
**Spec:** `docs/superpowers/specs/2026-09-20-generation-recovery.md`

## Global Constraints
- No automatic synthesis retries in this first version.
- Preserve completed audio, original text/settings, existing profiles and playback position.
- Default provider waits: 15s setup/connect/send, 60s audio inactivity, 180s whole segment, 5s close.
- Single FastAPI process; no extra queue infrastructure.

## Review Focus
- Closing a request/subscription cannot cancel server-owned work (task 2).
- A duplicate Resume cannot submit duplicate paid synthesis (task 2).
- Crash between writing audio and recording metadata cannot corrupt a completed checkpoint (task 2).
- Reopening History must refresh persisted state after missed events (task 3).
- Missing historical model or completed file must not trigger guessed synthesis/overwrite (task 2).

### Task 1: Bound Qwen synthesis and preserve diagnostics
Files: `providers/qwen.py`, `providers/base.py`, `config.py`, `providers/registry.py`, `tests/test_qwen_provider.py`, `tests/test_config.py`, configuration docs.
Interfaces: QwenTTSProvider accepts timeout keyword arguments; ProviderError remains a RuntimeError with human-readable diagnostic context.
- [ ] Write protocol fakes that withhold acknowledgement, audio, completion and close; test deadlines and error redaction. Verify failures before implementation.
- [ ] Implement acknowledgement-aware protocol and bounded connect/send/read/close. Keep audio inactivity independent of irrelevant events. Configure through Settings/environment.
- [ ] Run `PYTHONPATH=src .venv/bin/pytest -q tests/test_qwen_provider.py tests/test_config.py` and commit after green.

### Task 2: Durable checkpoints and owned background jobs
Files: `generation.py`, new `generation_jobs.py`, new `generation_storage.py`, `storage.py`, `routes/shared.py`, new `routes/generation_recovery.py`, `api.py`, focused recovery tests.
Interfaces: GenerationJobs.start(generation_id, *, resume=False, inline=False), cancel(generation_id), shutdown(); service.run_generation preserves completed segments. Storage.claim_generation atomically claims queued/failed jobs and rejects active/completed ones. Storage.complete_audio_segment commits audio metadata and text status together. Storage.interrupt_generations marks abandoned jobs failed.
- [ ] Test failed-second-segment recovery: retain first file/hash/audio ID, resume original settings after profile changes, no duplicate full audio.
- [ ] Test duplicate claims, malformed snapshots, missing completed files, restart interruption and cancellation during writes. Implement transactional storage and file publication.
- [ ] Test server tasks survive HTTP response/disconnect, and deletion waits for cancellation. Implement a task registry and lifespan startup/shutdown ownership.
- [ ] Add POST `/api/generations/{id}/resume` with 404/409/422 errors and shared Text/URL/OCR scheduling. Expose generation counts and resume eligibility in History/detail.
- [ ] Run focused generation/storage/API tests and commit after green.

### Task 3: Recovery UI and operational verification
Files: `static/history.js`, `static/app.js`, focused live-update helper, static version references, JS tests, `docs/architecture.md`, `docs/configuration.md`, `setup/envrc.local.example`, `setup/README.md`.
Interfaces: History Resume calls the recovery route then opens the existing generation. Active entries reconnect live progress using a persisted detail refresh on reconnect; closed views stop subscriptions only.
- [ ] Test Resume visibility, HTTP errors, preserved Open/Delete, generated-versus-listened progress and safe diagnostics.
- [ ] Test opening/reconnecting active generation and terminal state cleanup. Implement controls and a focused subscription helper.
- [ ] Document browser closure, shutdown/startup interruption, manual Resume, limits and single-process deployment.
- [ ] Run full Python, JS syntax/lint/tests, diff check, architecture review and live canary. Verify desktop/mobile UI and a real HTTP disconnect with fake synthesis. Commit final verified changes.
