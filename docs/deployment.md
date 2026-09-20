# Deployment

Readvox is intended to run as a localhost HTTP service. If remote access is needed, put a private HTTPS proxy in front of `127.0.0.1:8001` and grant access only to trusted devices.

The versioned systemd deployment files live in `setup/`:

- `setup/tts.service`: source-of-truth systemd unit for `/etc/systemd/system/tts.service`
- `setup/envrc.local.example`: environment file template for `/home/mohan/tts/.envrc.local`
- `setup/setup-venv.sh`: creates `.venv` and installs Python dependencies
- `setup/install-service.sh`: installs/enables the systemd service
- `setup/README.md`: lower-level install, update, diagnostics, and recovery commands

## One-Time Install

Follow [setup/README.md](../setup/README.md#one-time-install) to create the virtual environment, configure the private `.envrc.local`, populate the Qwen catalog, and install the service. The service reads environment changes after `sudo systemctl restart tts`. Built-in catalog updates need only an editor refresh.

## Trust Boundary

URL generation fetches pages server-side from the host running this app. Anyone who can access Readvox can ask that host to fetch arbitrary HTTP(S) URLs reachable from the machine. Do not expose the app publicly.
