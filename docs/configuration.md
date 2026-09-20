# Configuration And Providers

Readvox runs with deterministic fake providers by default for development and tests. Real TTS/OCR calls are isolated behind provider adapters.

## Fake Providers

Use fake providers for local UI work and automated tests:

```bash
TTS_PROVIDER=fake
OCR_PROVIDER=fake
```

The fake TTS provider writes deterministic audio-like files, not playable speech. The fake OCR provider returns deterministic text without calling external services. Fresh storage has an empty catalog and profile editor; tests supply fake catalog fixtures. See the [README](../README.md#local-development) for an isolated development command.

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

Populate the catalog before first use, with the intended storage settings loaded:

```bash
.venv/bin/python scripts/populate_voice_catalog.py --provider qwen --check
.venv/bin/python scripts/populate_voice_catalog.py --provider qwen
```

Population is offline and credential-free. It follows configured storage paths; `--data-dir /tmp/readvox-catalog-demo` overrides all paths for an isolated catalog. Check mode leaves the target database and sidecars unchanged. If a safe snapshot is blocked by an open connection or transaction, close that activity and rerun. Apply preserves stable IDs, reports model changes and marks retired presets unavailable. It leaves installed clones and profiles intact.

Startup reads the catalog without populating it. To add newly published presets, review and update `src/tts_app/providers/qwen_catalog.py` against the linked official [Qwen-TTS voice list](https://www.alibabacloud.com/help/en/model-studio/qwen-tts-voice-list), then rerun population. The command does not perform online discovery.

## Profiles and previews

Each catalog voice owns its provider, model, supported languages and instruction capability. Each profile stores its name, catalog `voice_id`, language, speed, instructions and preview text; profiles have no model field. Profiles are shared across devices. The browser remembers the selected profile per language.

Choose a profile in Generate and use **Edit**, or visit `/voice-sample`. Choose Language, then Base voice. **Preview** uses unsaved values; **Save** updates the selected profile and **Save As…** creates another with a unique name. In-app navigation preserves Text/URL/Image drafts. Text and URL use the selected profile's language; image generation requires one matching its OCR draft language. All profiles are editable and deletable. Deleting a profile leaves its catalog voice, enrollment, reference files, generated audio and History intact; deleted profiles do not reappear on startup or installation.

Voice samples accept preview text up to 50,000 characters, segmented with `TTS_SEGMENT_MAX_CHARS`. Their cache includes provider, model, voice, language, speed, instructions, text and segment boundary. **Clear samples** clears only preview audio. Previewing never creates a History entry.

`GET /api/voices` exposes read-only catalog identities and capabilities, without private provenance. `/api/voice-sample/options` provides `voice_catalog`, `default_voice_id`, language and speed choices. Profile writes accept `name`, `voice_id`, `language`, `speed`, `instructions`, and `preview_text`. Names are trimmed and case-insensitively unique; speed is 0.5–2.0, instructions are limited to 4,000 characters, and preview text must be nonempty. Model/voice capabilities and language validation are shared with preview synthesis.

UI generation requests send `profile_id`. The server snapshots the resolved profile name, voice, provider, model and reading settings before generation. Editing or deleting a profile cannot change active jobs or History. Unavailable voices and voices from another provider fail validation without substitution. API clients without a profile can send explicit voice/speed/language with the configured `TTS_MODEL` and empty instructions. Synthesis overrides alongside `profile_id` are rejected.

## Cloned voices

Use [Creating and reusing cloned voices](cloned-voices.md) for enrollment, comparison, installation, recovery and API details. Installation accepts an approved version-1 workshop manifest and adds catalog voices without creating profiles or making provider calls. The four saved narrators support English and `qwen3-tts-vc-realtime-2026-01-15`; instructions are disabled. Choose the clone and use **Save As…** to create a profile. Its catalog model takes precedence over the global `TTS_MODEL` default.

Back up SQLite, `data/voices/`, and complete private workshop runs together. Startup does not scan reference directories or enroll automatically. Clearing samples or deleting profiles/History does not remove catalog voices or reference bundles.

## Live provider integration

The live provider integration canary makes one short paid Text API request through a saved profile in temporary storage. It does not write production History. Run once before marking an implementation feature complete:

```bash
set -a
source .envrc.local
set +a
RUN_QWEN_INTEGRATION=1 .venv/bin/pytest -m live_provider -q
```

It normally uses an instruction profile. To reuse the saved Kai enrollment instead, set `QWEN_LIVE_CLONE_MANIFEST` to the absolute path of an accepted version-1 manifest containing `readvox-kai-v1`:

```bash
QWEN_LIVE_CLONE_MANIFEST=/home/mohan/tts/data/voice-workshop/narrators-v1/manifest.json RUN_QWEN_INTEGRATION=1 .venv/bin/pytest -m live_provider -q
```

This installs the saved catalog voice and creates a profile in temporary storage; it never enrolls. These commands are alternatives for the single canary.

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

The historical flash-model prices above do not establish instruction-model pricing. Re-check Alibaba Cloud pricing before implementing any billing-sensitive behavior.
