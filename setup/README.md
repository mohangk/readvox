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

Copy the environment example only if `.envrc.local` does not exist, set the API key and adjust `TTS_DATA_DIR` if needed:

```bash
cp setup/envrc.local.example .envrc.local
chmod 0600 .envrc.local
```

Then [populate the built-in catalog](#populate-or-refresh-built-in-voices) and run the systemd setup script:

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

3. [Populate the built-in catalog](#populate-or-refresh-built-in-voices), then install the unit file and enable the service:

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

Wait for active generations to finish and make a [backup](#backups-and-cloned-voices) before updating.

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

## Populate or refresh built-in voices

Load the deployment environment so the command uses the service's database:

```bash
set -a
source .envrc.local
set +a
.venv/bin/python scripts/populate_voice_catalog.py --provider qwen --check
.venv/bin/python scripts/populate_voice_catalog.py --provider qwen
```

Run before first use and when the reviewed Qwen catalog source changes. Population is offline and requires no credentials. Check mode leaves the database and sidecars unchanged; if an active connection prevents a safe snapshot, close that activity and rerun. The command reports changes and preserves existing IDs, profiles and clones. `--data-dir /tmp/readvox-catalog-demo` overrides storage paths for an isolated run. Refresh the editor after updates; catalog changes need no restart. Startup reads the catalog without repopulating it.

## Backups and cloned voices

Before updating an existing deployment, wait until `/api/generations` has no `queued` or `running` jobs. Keep the app idle while making a consistent SQLite backup using SQLite's backup API or `.backup`; copying only an active main database file can omit committed WAL data. Back up configured audio, images, `data/voices/` and complete private workshop runs with the database. Rollback of a schema change requires its matching database backup and code.

Existing catalog voices and profiles are used directly from SQLite. To install accepted version-1 clone bundles on a fresh database or create new clones, follow [Creating and reusing cloned voices](../docs/cloned-voices.md). Installation is offline and creates catalog entries, not profiles. Choose an installed clone in **Edit**, set reading settings and use **Save As…**. Retain original source bundles for repeat installs; conflicting definitions or provenance are rejected.

For the single paid development canary, see [Live provider integration](../docs/configuration.md#live-provider-integration).

### Background jobs and interrupted generations

Run one Uvicorn worker/process per Readvox database. Jobs belong to the server, so closing browser tabs does not stop synthesis. Reopening an active History entry reconnects progress. Deploy/reload after active work completes when possible: a shutdown cancels owned jobs, and startup marks abandoned queued/running entries failed with an interruption message. Use **Resume** in History to continue with the original saved settings and retained completed audio. Startup never automatically makes paid synthesis requests.

Qwen wait limits are configured in `envrc.local.example`; failures include safe stage/request/session diagnostics for provider support. Listing cloud voices (`scripts/voices.py list`) checks enrollment existence, not synthesis health.
