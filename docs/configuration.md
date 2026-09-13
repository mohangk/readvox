# Configuration And Providers

Readvox runs with deterministic fake providers by default for development and tests. Real TTS/OCR calls are isolated behind provider adapters.

## Fake Providers

Use fake providers for local UI work and automated tests:

```bash
TTS_PROVIDER=fake
OCR_PROVIDER=fake
```

The fake TTS provider writes small deterministic audio-like files. The fake OCR provider returns deterministic text without calling external services.

## Qwen Providers

```bash
TTS_PROVIDER=qwen
OCR_PROVIDER=qwen
DASHSCOPE_API_KEY=...
TTS_MODEL=qwen3-tts-instruct-flash-realtime
OCR_MODEL=qwen-vl-ocr
QWEN_REALTIME_URL=wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime
TTS_DEFAULT_ENGLISH_VOICE=Kai
TTS_DEFAULT_CHINESE_VOICE=Cherry
```

`DASHSCOPE_API_KEY` is preferred. `QWEN_API_KEY` is also supported where provider code accepts it.

Generate uses named voice profiles shared across devices in SQLite. Choose a profile and use **Edit** to preview or change its settings. Every profile is editable and deletable; **Save As…** creates another named profile. Text and URL list all named voices and use the selected voice’s language; Image lists voices compatible with the separate OCR language. Each profile stores its name, catalog `voice_id`, selected model, language, speed, instructions, and editable preview text. The backend-managed catalog holds provider identities and compatible models for built-in and cloned voices. English and Chinese audiobook defaults use the instruction model, Kai, and 1× speed. Profile names are trimmed and case-insensitively unique, including Unicode case folding.

The same editor is available at `/voice-sample`. **Preview** uses unsaved values; **Save** updates the selected profile, while **Save As…** asks for a unique name and creates a new profile from the current settings. Both select the saved voice and return to Generate. Save, Save As, and Cancel are at the top, followed by the saved-voice selector. **Cancel** keeps saved values unchanged and warns before discarding edits. In-app navigation preserves Text/URL input, Image review text, source images, and the originating Generate mode. OCR recognition language remains separate: image generation requires a profile matching its draft language.

The browser remembers the selected profile for each language. A deleted selection falls back to the first available profile for that language. If none remain, create a new profile. Legacy voice preferences and `readvox.voiceSelection.v1` remain stored. The editor has no import, duplicate, or new controls; use Save As to create profiles. Choose Language, then Base voice. Each option identifies its provider. A bilingual voice appears once under either language; changing to an incompatible language requires another voice selection. There is no model selector. Existing voices using the legacy flash model remain editable with empty instructions.

Voice samples accept preview text up to 50,000 characters and use the same `TTS_SEGMENT_MAX_CHARS` boundary as generation. Preview audio is cached by provider, model, voice, language, speed, instructions, text, and segment boundary; renaming a profile does not invalidate its audio. **Clear samples** clears only preview audio. Previewing never creates a History entry. Deleting a profile leaves its catalog voice, enrollment, reference files, generated audio and History intact. Startup and clone reinstallation do not recreate deleted profiles.

New Text, URL, and OCR UI requests send `profile_id`. The server resolves it once and snapshots profile ID/name, catalog voice ID, friendly voice name, provider, model, raw voice ID, language, speed, and instructions into the generation. History displays and searches those saved friendly labels. Editing or deleting a profile cannot alter an existing job. API clients without a profile retain explicit voice/speed/language, use the configured `TTS_MODEL`, and have empty instructions. Supplying synthesis overrides with `profile_id` returns a validation error. Existing history is unchanged; missing historical model metadata remains unknown.

`GET /api/voices` exposes the read-only catalog: ID/key, provider and provider voice ID, friendly name, built-in/cloned kind, availability, one model, supported languages and instruction capability. Enrollment and reference provenance remain private. `/api/voice-sample/options` includes `voice_catalog` and `default_voice_id` alongside language and speed choices.

The profile API provides `GET/POST /api/voice-profiles` and `GET/PUT/DELETE /api/voice-profiles/{id}`. Creation and update accept `name`, `voice_id`, `language`, `speed`, `instructions`, and `preview_text`. Preview requests to `POST /api/voice-sample/instruction` also use `voice_id`; the backend resolves the model. Legacy clients can send raw `voice` plus model; explicit conflicting identity/model fields are rejected. Profile responses include derived `provider`, raw `voice`, `voice_name` and `voice_key`. Names are required, speed is 0.5–2.0, instructions have a 4,000-character limit, and preview text must be nonempty. Model/voice capabilities and language validation are shared with preview synthesis.

The explicit catalog population command supplies built-in provider/model bindings and language capabilities. Later refreshes mark removed built-ins unavailable so existing profiles keep their identity. Requests for an unavailable voice or one belonging to a different provider fail without substitution. Future providers require an adapter and configuration; the catalog schema alone does not activate them.

Populate built-in voices explicitly before first use:

```bash
.venv/bin/python scripts/populate_voice_catalog.py --provider qwen --check
.venv/bin/python scripts/populate_voice_catalog.py --provider qwen
```

The command is offline and credential-free. Preflight takes a short exclusive SQLite-compatible file lock on this POSIX deployment and recovers any journals only in a private copy. If a connection or transaction prevents a safe snapshot, it exits with an idle-database diagnostic; close that activity before rerunning. Check mode leaves the target database and sidecars unchanged. The explicit `--provider qwen` also supplies the ownership context for older raw-voice profiles; invalid provider configuration is rejected before target access. It follows configured storage paths; `--data-dir /tmp/readvox-catalog-demo` targets isolated storage. It reports added, updated, unchanged and retired entries, including model changes. Update the reviewed source in `src/tts_app/providers/qwen_catalog.py` from the official [Qwen-TTS voice list](https://www.alibabacloud.com/help/en/model-studio/qwen-tts-voice-list), then rerun to add new presets. It does not discover newly published voices automatically. App startup reads the catalog without resynchronizing it. Built-in updates leave clones and profiles intact. Profiles have no model field; catalog model changes affect future synthesis while active jobs retain snapshots.

The live provider integration canary verifies a saved profile through the complete generation API-to-Qwen path with one short paid Text API request in a temporary database/data directory. By default it uses an instruction profile. Set `QWEN_LIVE_CLONE_MANIFEST` to the absolute path of the exact approved historical manifest to install only the Kai Narrator catalog voice and create a personal profile through the API in that temporary database, reusing its saved enrollment without an enrollment create request. Deterministic tests cover multi-segment sample assembly without adding paid provider calls. Run the canary once before marking an implementation feature complete:

```bash
set -a
source .envrc.local
set +a
RUN_QWEN_INTEGRATION=1 .venv/bin/pytest -m live_provider -q
```

For the single saved-clone canary, run this instead of an additional instruction canary:

```bash
QWEN_LIVE_CLONE_MANIFEST=/home/mohan/tts/src/tts_app/static/clone-lab-data/20260913T043114Z-0f3d936a/manifest.json RUN_QWEN_INTEGRATION=1 .venv/bin/pytest -m live_provider -q
```

## Cloned Catalog Voices

The offline `scripts/voices.py install` command adds approved enrollments to the same SQLite catalog as built-in voices: **Kai Narrator**, **Vivian Narrator**, **Bellona Narrator**, and **Neil Narrator**. They support English and the pinned `qwen3-tts-vc-realtime-2026-01-15` model, with instructions disabled. Installation never creates profiles. On a clean installation, choose a clone in the editor, set reading settings, and use **Save As…**. The global `TTS_MODEL` remains the instruction-model default; the catalog voice supplies the model captured in each generation snapshot.

Migration 4 moves model ownership to voices and retains compatible profiles, including the four approved narrator settings. It reports any binding changes and authorized incompatible-record cleanup; it leaves independent History and media unchanged. Existing clones keep their exact enrollment model, so no manual clone reinstall is needed. Accepted reference/evaluation speeds remain provenance rather than profile defaults.

Clone capabilities come from installed catalog entries and the active provider. Arbitrary cloud IDs are rejected. Profiles can reuse a clone with another name or speed, with no new enrollment. Nonempty clone instructions or an incompatible language are rejected.

Reference WAVs and input manifests are durable under `$TTS_DATA_DIR/voices/`, outside the preview cache. SQLite remains authoritative for installed catalog entries. Startup does not scan voice directories or enroll automatically. Back up the database, `data/voices/`, and complete private source/workshop directories. Clearing samples or deleting profiles/History does not delete catalog voices or references. See [creating and reusing cloned voices](cloned-voices.md) for supplied-WAV enrollment, comparison, inspection, explicit acceptance, interruption recovery, and offline historical import/install; see the [rollout sequence](../setup/README.md#unified-voice-catalog-rollout) before updating the live process.

## Runtime Storage Settings

| Variable | Default | Purpose |
| --- | --- | --- |
| `TTS_DATA_DIR` | `data` | Root directory for local SQLite data and generated files. |
| `TTS_DB_PATH` | `$TTS_DATA_DIR/app.db` | SQLite database path. |
| `TTS_AUDIO_DIR` | `$TTS_DATA_DIR/audio` | Generated audio directory, including per-generation audio and voice sample cache files. |
| `TTS_IMAGE_DIR` | `$TTS_DATA_DIR/images` | Stored OCR source image directory. |
| `TTS_AUDIO_EXT` | `mp3` | Default generated audio file extension. |
| `TTS_SEGMENT_MAX_CHARS` | `550` | Maximum text characters per generated TTS segment. |
| `TTS_MAX_IMAGE_BYTES` | `10485760` | Maximum accepted OCR source image size. |

## OCR Image Mode

Image mode lets you upload or capture one or more photographed/scanned pages, review OCR text beside image thumbnails, choose an English or Chinese voice, and create a normal streamed generation from the combined reviewed text.

```bash
OCR_PROVIDER=fake
OCR_MODEL=qwen-vl-ocr
TTS_IMAGE_DIR=data/images
TTS_MAX_IMAGE_BYTES=10485760
```

Uploaded source images are stored under `data/images/` while their OCR draft exists. Deleting an unlinked OCR draft removes its stored image directory. Deleting a History entry created from an OCR draft removes the generation, cached audio, linked OCR draft, and stored source image directory.

For Chinese OCR, preserve only visible Chinese text and visible pinyin. Do not generate missing pinyin, transliterate Chinese characters into pinyin, translate, summarize, or infer text that is not visible in the image.

## Pricing Context

Alibaba Cloud Model Studio pricing is documented at <https://www.alibabacloud.com/help/en/model-studio/model-pricing>. The pricing page was last updated by Alibaba on Jun 22, 2026.

For the previously used realtime TTS model, `qwen3-tts-flash-realtime`, the relevant text-to-speech pricing captured on May 02, 2026 is:

| Deployment mode | Model | Billing unit | Input price | Output price | Free quota |
| --- | --- | --- | --- | --- | --- |
| International | `qwen3-tts-flash-realtime` | Input text characters | `$0.13 / 10K characters` | Not billed | 10,000 characters, valid 90 days after activating Model Studio |
| Chinese Mainland | `qwen3-tts-flash-realtime` | Input text characters | `$0.143353 / 10K characters` | Not charged | No free quota |

Future cost tracking should store the model, deployment mode, input character count, pricing source date, and calculated estimated cost per generation. Pricing can change, so keep this as a documented baseline rather than hard-coding it as permanent billing truth.

## Legacy Environment Cleanup

Existing deployments should use `TTS_MODEL`, `OCR_MODEL`, and `OCR_PROVIDER=qwen`. Remove old `QWEN_MODEL`, `QWEN_OCR_MODEL`, and `QWEN_VOICE` entries from `.envrc.local`.

The historical flash-model prices above do not establish instruction-model pricing. Re-check Alibaba Cloud pricing before implementing any billing-sensitive behavior.
