# Deploying Readvox

This folder is the source of truth for the VPS deployment. The unit file in
`/etc/systemd/system/` should be installed from `tts.service` in this
folder.

The setup mirrors `time-consumer`: a localhost-bound development server runs
under systemd with reload enabled. If remote access is needed, put a private
HTTPS proxy in front of `127.0.0.1:8001`.

## One-time install

Prerequisite: repo cloned at `/home/mohan/tts`.

Run the venv setup script:

```bash
cd /home/mohan/tts
setup/setup-venv.sh
```

Run the systemd setup script:

```bash
setup/install-service.sh
```

The venv script creates `.venv` if needed and installs dependencies. The systemd
script creates `.envrc.local` from the example if it is missing and
installs/enables the service.

Manual equivalent:

1. Create the venv and install dependencies:

   ```bash
   python -m venv .venv
   .venv/bin/pip install -e ".[dev]"
   ```

2. Copy `setup/envrc.local.example` to `/home/mohan/tts/.envrc.local`, fill in
   the real DashScope API key, and restrict permissions:

   ```bash
   cp setup/envrc.local.example .envrc.local
   chmod 0600 .envrc.local
   ```

3. Install the unit file and enable the service:

   ```bash
   sudo install -m 0644 setup/tts.service /etc/systemd/system/tts.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now tts
   ```

4. Verify locally:

   ```text
   http://127.0.0.1:8001
   ```

## Qwen API key

Put the key in `/home/mohan/tts/.envrc.local`:

```bash
DASHSCOPE_API_KEY=<your-key>
```

The systemd unit reads this file through `EnvironmentFile=`. After changing the
key, restart the service:

```bash
sudo systemctl restart tts
```

## Day-to-day update flows

### Code edits

```bash
cd /home/mohan/tts
git pull
```

Uvicorn's reloader detects Python changes under `src/`. Frontend assets usually
only need a browser refresh. Confirm reloads with:

```bash
journalctl -u tts -f
```

### Dependency change

```bash
cd /home/mohan/tts
git pull
.venv/bin/pip install -e ".[dev]"
sudo systemctl restart tts
```

### Unit file or env file change

```bash
cd /home/mohan/tts
git pull
sudo install -m 0644 setup/tts.service /etc/systemd/system/tts.service
sudo systemctl daemon-reload
sudo systemctl restart tts
```

Edits to `.envrc.local` are picked up on service restart. They do not require
`daemon-reload`.

## Diagnostics

```bash
systemctl status tts
journalctl -u tts -f
ss -ltnp | grep :8001
```

## Failure modes

| Mode | Symptom | Recovery |
|---|---|---|
| SyntaxError after `git pull` | Reloader logs traceback; previous worker may keep serving | Save a fix; reloader re-imports |
| Missing API key | Qwen generations fail with provider auth errors | Add `DASHSCOPE_API_KEY` to `.envrc.local`; restart |
| Env file missing | Unit fails during startup | Copy `setup/envrc.local.example` to `.envrc.local`; restart |
| Port 8001 already in use | Unit fails with address-in-use error | `ss -ltnp \| grep :8001`, stop the conflicting process, restart |

### Named voice profile upgrade

Set the local `.envrc.local` override to `TTS_MODEL=qwen3-tts-instruct-flash-realtime` before restarting; a preexisting `TTS_MODEL` overrides the new default. New installations use `TTS_DEFAULT_ENGLISH_VOICE=Kai`, a supported instruction voice. Review any explicit legacy default voice override separately; profile generations snapshot the selected catalog voice's provider/model. Keep credentials local and uncommitted.

Check `/api/generations` for `queued` or `running` work and wait for it to finish before restarting `tts.service`. After catalog population, startup adds profile tables and editable English/Chinese defaults without rewriting generation settings or touching cached audio. Profiles are shared across devices; selected profile IDs are browser-local.

### Unified voice catalog rollout

This code-only upgrade migrates already installed voices and profiles locally. Keep `TTS_MODEL=qwen3-tts-instruct-flash-realtime`, `.envrc.local` and provider credentials unchanged. It makes no enrollment or synthesis requests and requires no manual clone reinstall for existing installed data.

1. Check `/api/generations` and wait until no work is `queued` or `running`. Keep the app idle through backup, migration and code reload so reload cannot interrupt synthesis.
2. Make a private, consistent SQLite backup using SQLite's backup API or `.backup`, and copy all configured data directories, including `data/audio/`, `data/images/` and `data/voices/`. Also retain complete private workshop/legacy directories: source manifests can refer to comparison assets there. Do not rely on copying only an active SQLite main file when WAL files may contain committed data.
3. Apply the reviewed code update to the live checkout. The existing Uvicorn `--reload` process detects Python changes under `src/`. Startup runs migration 4 once and reads the catalog. Built-in updates are explicit: run `scripts/populate_voice_catalog.py --provider qwen --check` in the reviewed checkout first, inspect any migration cleanup/model changes, then apply without `--check` while idle. No environment change or `systemctl restart` is needed. Follow `journalctl -u tts -f`, then refresh the browser.
4. Verify `GET /api/voices` lists built-in and installed cloned voices with one model and supported languages per voice. Verify `/api/voice-profiles` preserves existing profile IDs, settings and timestamps, including **Kai Narrator** (1×), **Vivian Narrator** (1.1×), **Bellona Narrator** (1.25×), and **Neil Narrator** (1×). All profiles now support ordinary Save and Delete; **Save As…** creates another profile. Confirm Text/URL selection, English Image language filtering and friendly saved History labels without changing existing audio.

Migration removes the old registry/system/raw-profile columns, the profile model column and multiple-model voice capabilities. Compatible profile identities/settings remain; the migration reports changed model bindings and authorized cleanup of incompatible records. Independent generation History, audio/images and reference bundles remain untouched. Deleted profiles never return through startup or installation. Retain the pre-migration backup because schema rollback requires restoring both database and code.

### Populate or refresh built-in Qwen voices

Run before starting a fresh app, or explicitly when the reviewed Qwen catalog source changes:

```bash
.venv/bin/python scripts/populate_voice_catalog.py --provider qwen --check
.venv/bin/python scripts/populate_voice_catalog.py --provider qwen
```

No credentials or network calls are required. Preflight takes a short exclusive SQLite-compatible file lock on this POSIX deployment and recovers any journals only in a private copy. If a connection or transaction prevents a safe snapshot, it exits with an idle-database diagnostic; close that activity before rerunning. Check mode leaves the target database and sidecars unchanged. The explicit `--provider qwen` also supplies the ownership context for older raw-voice profiles; invalid provider configuration is rejected before target access. The command shows the configured database target; `--data-dir /tmp/readvox-catalog-demo` creates an isolated catalog. Check mode creates no files and upgrades no target schema. Apply is transactional, preserves stable IDs and unchanged timestamps, and marks removed presets unavailable. It does not modify profiles, installed clones or another provider's entries. Refresh the editor after a successful update; no service restart is needed for catalog data changes.

Review and update `src/tts_app/providers/qwen_catalog.py` against its linked official source to add newly published voices. Running the existing source again is idempotent, not online discovery. App startup does not repopulate the catalog. Empty startup serves a clear empty editor; ordinary defaults are seeded once when compatible voices are available. Deleting profiles never resets that marker.

### Installing clones on a clean deployment

Existing installed data needs only the migration above. To add the four approved enrollments to a fresh deployment, load its local environment and run the offline installer after making a private backup and keeping the app idle:

```bash
cd /home/mohan/tts
set -a
source .envrc.local
set +a
.venv/bin/python scripts/voices.py install --manifest /home/mohan/tts/src/tts_app/static/clone-lab-data/20260913T043114Z-0f3d936a/manifest.json --check
.venv/bin/python scripts/voices.py install --manifest /home/mohan/tts/src/tts_app/static/clone-lab-data/20260913T043114Z-0f3d936a/manifest.json
```

Check mode makes no writes or provider calls. Installation verifies the exact historical manifest and reference fingerprints, copies durable reference bundles/source metadata, and adds only catalog voices. It never creates or recreates profiles. Conflicting keys/provider identities, changed definitions or modified historical approval inputs are rejected. Existing original files remain intact; failed database writes retain their reference bundle for recovery. Preserve retained bundles instead of automatically deleting them.

Refresh the editor, choose a language and clone, then reading settings, then use **Save As…** to create a profile. Accepted reference/evaluation speeds remain manifest provenance, so the catalog stores no active profile defaults. SQLite is authoritative; startup does not automatically import files or reenroll. Back up SQLite and `data/voices/` together, while retaining complete source runs for inspection. Preview-cache clearing and profile/History deletion do not remove these references. See [Creating and reusing cloned voices](../docs/cloned-voices.md) for maintained workshop commands and interruption recovery.

The optional integration canary installs the same saved Kai catalog voice in a temporary database, creates a personal profile through the API, and makes one short paid Text API request, without enrollment or production History writes. Run it once in the reviewed checkout after deterministic checks, with local credentials loaded:

```bash
QWEN_LIVE_CLONE_MANIFEST=/home/mohan/tts/src/tts_app/static/clone-lab-data/20260913T043114Z-0f3d936a/manifest.json RUN_QWEN_INTEGRATION=1 .venv/bin/pytest -m live_provider -q
```

Without `QWEN_LIVE_CLONE_MANIFEST`, the existing canary uses an instruction profile instead. These are alternatives for the single canary, not a reason to perform a second paid check.
