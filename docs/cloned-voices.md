# Creating and reusing cloned voices

Enroll a recording once, save its cloud voice ID and exact target model, and reuse that pair for new speech. **Kai Narrator, Vivian Narrator, Bellona Narrator and Neil Narrator are already enrolled.** Select an installed voice in the profile editor; changing a profile's name or speed requires no new enrollment.

Use [`scripts/voices.py`](../scripts/voices.py) from the repository root. It keeps private workshop files outside production History. `--check` validates locally without writes or provider requests. `candidates`, new `enroll`, and `compare` make paid requests when run without `--check`; `inspect` and `install` are offline.

## The APIs

| Boundary | What it does |
| --- | --- |
| Qwen HTTPS customization | `action=create` uploads reference audio and returns a reusable voice ID bound to a target model. Explicit `action=list` recovers an enrollment after an interrupted request. |
| Qwen realtime WebSocket | Generates new text using the saved voice/model pair, without uploading the reference again. |
| Readvox HTTP | Reads the local catalog, saves profiles, previews settings, and generates Text/URL/Image audio. |

The enrollment endpoint is derived from `QWEN_REALTIME_URL`. For the international region these are:

```text
https://dashscope-intl.aliyuncs.com/api/v1/services/audio/tts/customization
wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime
```

Keep enrollment and synthesis in the same account and region. The adapter supports the international, mainland China and US DashScope hosts. Credentials come from `DASHSCOPE_API_KEY` or `QWEN_API_KEY`; load them locally before paid commands:

```bash
set -a
source .envrc.local
set +a
```

The [enrollment adapter](../src/tts_app/providers/qwen_enrollment.py) sends an audio-only request with bearer authentication:

```json
{
  "model": "qwen-voice-enrollment",
  "input": {
    "action": "create",
    "target_model": "qwen3-tts-vc-realtime-2026-01-15",
    "preferred_name": "readvoxkai123456",
    "language": "en",
    "audio": {"data": "data:audio/wav;base64,<encoded WAV>"}
  }
}
```

`qwen-voice-enrollment` selects the enrollment service. `target_model` selects later synthesis. The tool saves `output.voice`, `output.target_model` and request metadata in a version-1 workshop manifest. It writes the pending state before create and never automatically retries an uncertain enrollment.

For synthesis, the [TTS adapter](../src/tts_app/providers/qwen.py) places that model in the WebSocket URL and sends `session.update` with the saved voice, language, speed and audio format, followed by `input_text_buffer.append`, `input_text_buffer.commit`, and `session.finish`. It collects `response.audio.delta` bytes and requires successful `response.done` with nonempty audio. Clone instructions are empty. See the provider's [customization API](https://www.alibabacloud.com/help/en/model-studio/voice-clone-design-http-api), [client events](https://www.alibabacloud.com/help/en/model-studio/qwen-tts-realtime-client-events) and [server events](https://www.alibabacloud.com/help/en/model-studio/qwen-tts-realtime-server-events).

## Create a new clone

Supply a complete mono 16-bit WAV, at least 24 kHz, 3–60 seconds, and at most 10 MiB. The maintained enrollment workflow supports English and `qwen3-tts-vc-realtime-2026-01-15`.

```bash
.venv/bin/python scripts/voices.py enroll --reference selected.wav --name "My Narrator" --key my-narrator-v1 --model qwen3-tts-vc-realtime-2026-01-15 --speed 1 --output data/voice-workshop/my-narrator-v1 --check
.venv/bin/python scripts/voices.py enroll --reference selected.wav --name "My Narrator" --key my-narrator-v1 --model qwen3-tts-vc-realtime-2026-01-15 --speed 1 --output data/voice-workshop/my-narrator-v1
```

Use a new directory and stable key for each enrollment revision. The name is a local display label; the returned provider ID identifies the cloud resource. Keep the WAV and any known source text/settings with the run.

To generate candidate reference recordings first, provide a UTF-8 text file and an explicit matrix:

```bash
.venv/bin/python scripts/voices.py candidates --text reference.txt --voices Kai Vivian Bellona Neil --speeds 1 1.1 1.25 --output data/voice-workshop/candidates --check
```

Remove `--check` to synthesize. Candidates default to the instruction model and audiobook instructions; `--model`, `--language` and `--instructions <UTF-8-file>` override these. When enrolling a completed candidate, add `--candidate-manifest <manifest.json> --sample <number>` to retain and verify its source settings. English enrollment requires an English candidate.

Compare the enrollment on unfamiliar UTF-8 passages, each 1–2000 characters. `--passages` accepts a text file or a directory of ordered `.txt` files. Each passage makes an independent synthesis request:

```bash
.venv/bin/python scripts/voices.py compare --manifest data/voice-workshop/my-narrator-v1/manifest.json --passages passages/ --speeds 1 1.1 1.25 --check
.venv/bin/python scripts/voices.py compare --manifest data/voice-workshop/my-narrator-v1/manifest.json --passages passages/ --speeds 1 1.1 1.25
.venv/bin/python scripts/voices.py inspect --manifest data/voice-workshop/my-narrator-v1/manifest.json
```

`compare` reuses the enrollment. Optionally add `--control-manifest <candidate-manifest> --control-sample <number>` to compare its original candidate configuration, or `--output <new-directory>` for a separate comparison run. Listen to the run's `report.html`; it links local audio and shows incomplete or failed passages. After listening, accept a completed comparison at a tested speed and install it:

```bash
.venv/bin/python scripts/voices.py install --manifest data/voice-workshop/my-narrator-v1/manifest.json --accept my-narrator-v1 --speed 1 --check
.venv/bin/python scripts/voices.py install --manifest data/voice-workshop/my-narrator-v1/manifest.json --accept my-narrator-v1 --speed 1
```

Installation accepts only version-1 workshop manifests. It checks assets and comparisons, records acceptance, copies durable reference bundles under `data/voices/`, and adds catalog voices. It never enrolls or creates profiles. Repeating the same definition is idempotent; conflicting keys, provider IDs or provenance are rejected. Accepted evaluation speeds remain provenance; choose your reading speed in a profile.

## Reuse or restore saved voices

The four existing narrators are English voices with the pinned clone model and no instructions. On the current installation, select them directly. SQLite stores their catalog identities and profiles; startup reads that database without scanning manifests.

For an empty database, restore the saved accepted version-1 bundle offline:

```bash
.venv/bin/python scripts/voices.py install --manifest data/voice-workshop/narrators-v1/manifest.json --check
.venv/bin/python scripts/voices.py install --manifest data/voice-workshop/narrators-v1/manifest.json
```

This private bundle contains existing enrollments and recordings; it is not included in Git. Use a consistent database and data-directory backup to restore an existing installation. The portable bundle restores catalog voices into empty storage, but does not recreate saved profiles. Installing a differently packaged bundle over existing entries can be rejected because its provenance differs; retain the original installation source for repeat installs.

Open **Edit** or `/voice-sample`, choose a language and voice, set reading settings, and use **Save As…** with a unique profile name. **Save** updates the selected profile. Catalog voices own their model and supported languages; profiles store `voice_id`, name, language, speed, instructions and preview text. Clone instructions stay empty. Text, URL and reviewed English Image drafts can use clone profiles.

| Readvox API | Purpose |
| --- | --- |
| `GET /api/voices` | Read catalog identities and capabilities; excludes private provenance. |
| `GET/POST /api/voice-profiles` | List or create profiles with `voice_id` and reading settings. |
| `GET/PUT/DELETE /api/voice-profiles/{id}` | Read, edit or delete a profile. |
| `POST /api/voice-sample/instruction` | Preview explicit `voice_id` and reading settings without History. |
| `POST /api/generations/text` or `/api/generations/url` | Generate with a saved `profile_id`. |
| `POST /api/ocr-drafts/{draft_id}/generation` | Generate reviewed text with a language-compatible profile. |

The configured provider must support the selected catalog voice. Each generation snapshots its model, voice and profile settings, so later edits do not change History. Profile deletion leaves the enrollment, references and generated audio intact. For built-in catalog population, see [Configuration](configuration.md).

## Resume interrupted work

Candidates and comparisons accept `--resume <manifest.json>` with the original inputs; completed audio is retained and only remaining requests run. Inspect an uncertain enrollment locally, then explicitly look it up instead of creating another:

```bash
.venv/bin/python scripts/voices.py inspect --manifest data/voice-workshop/my-narrator-v1/manifest.json
.venv/bin/python scripts/voices.py enroll --resume data/voice-workshop/my-narrator-v1/manifest.json --lookup --page-index 0
.venv/bin/python scripts/voices.py enroll --resume data/voice-workshop/my-narrator-v1/manifest.json --adopt-voice-id <recovered-voice-id> --page-index 0
```

Lookup sends `action=list` with `page_index` and `page_size=100`. Check subsequent pages as needed and match the saved preferred name and creation details. Adoption checks the returned voice's model, region and credentials before saving it. After confirming a rotated key belongs to the same account, use `--acknowledge-credential-change`. Normal inspection, installation and app startup never contact the enrollment API.

## Backups

Back up SQLite consistently, `data/voices/`, and complete private workshop runs together. Manifests use relative asset paths and SHA-256 checksums. Installed `source.json` retains manifest metadata, but comparison audio remains in the workshop run. Retain bundles after failed installation for recovery, and keep all private recordings, manifests and credentials out of Git. Preview-cache clearing and profile/History deletion do not remove voice references. Workshop files have no automatic cleanup; deleting local files does not delete a cloud enrollment.
