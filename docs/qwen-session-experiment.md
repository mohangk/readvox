# Qwen session listening experiment

These are archived experiment instructions for branch `experiment/qwen-session-consistency` at commit `e6a031b`. The lab pages and runners below are not part of the production system-profile checkout. Existing recordings remain private; use the maintained cloning guide linked below to import or reuse them.

For enrollment APIs, saved voice IDs, recovery, and future reuse of the four
approved voices, read [Creating and reusing cloned voices](cloned-voices.md).

Open `/static/session-lab.html` on the running Readvox host. This is an isolated,
pre-generated comparison, with no new routes or changes to normal generation.
Playback and refresh do not make paid requests.

Version A uses the existing Qwen provider, opening a connection for each segment.
Version B uses an experimental adapter that sends the same consecutive segments
as successive commits on one connection. It waits for each completed response
before committing the next and finishes the session only after the last response.
Both versions use the source generation's recorded model, voice, speed, language,
and instructions. Neither re-reads the mutable voice profile. Both request 24 kHz
16-bit mono PCM, wrapped in WAV for playback; no silence or normalization is added.
Thus the baseline follows the production session lifecycle, with a lossless output
format chosen for exact concatenation and boundary markers.

The initial comparison uses six original consecutive segments starting at the
first paragraph with at least 200 characters in the latest URL generation. Short
paragraphs inside the excerpt remain untouched. This selection skips leading
navigation for the listening sample; it does not implement article extraction or
resegmentation. Boundary buttons start two seconds before each transition.

To generate another pair (paid Qwen calls), from the repository root:

```bash
set -a
source .envrc.local
set +a
.venv/bin/python -m tts_app.experiments.qwen_session_lab
```

Optional arguments: `--generation-id 64 --start-segment 11 --segments 6`.
To add version C to the existing comparison without regenerating A or B, run the
same command with `--add-continuous --continuous-segments 5`. This reads the saved
comparison snapshot and joins the first five paragraphs into one append and one
commit through the existing provider. Qwen rejected the full 2,110-character
excerpt both as one append and as multiple appends before one commit: the
2,000-character limit applies to the combined text. C therefore covers the first
five complete paragraphs (1,584 characters including paragraph separators).
The page explicitly labels this shorter scope; compare the first five paragraphs
of A/B with C. No text inside those paragraphs is rewritten. The CLI rejects
text over 2,000 characters before calling Qwen; provider validation still applies
(in particular to language-specific character accounting).
It saves C in a new run directory
and retains A/B's original audio paths. A failed request leaves the published
comparison unchanged. C has a full-passage player, without invented segment
timestamps; the boundary buttons remain specific to A/B. This tests a single
synthesis response, independently of the prior connection-reuse experiment.

The start index is zero-based; the page displays original segment numbers starting
at one. The command defaults to the local read-only History API at port 8001.
Use `--api-url` to change that address. It requires recorded synthesis settings,
and limits each version to 2–12 segments and at most 8,000 characters.

Generated files live in ignored `src/tts_app/static/session-lab-data/<run-id>/`.
They include source text, individual segment WAVs, combined tracks, and a manifest
with measured boundary times and connection counts. Treat this directory as local
private data, served through the same trusted Readvox host. Never commit it.
The latest pointer is replaced only after both tracks complete. Failed runs retain
partial files, and earlier runs remain available on disk; nothing is automatically
deleted. Removal, if desired, is an explicit manual action limited to the chosen
experiment directory. These disposable artifacts intentionally have no SQLite
relationship, unlike durable production generation audio. They are excluded from
the application's packaged static assets.

One pair is a listening probe, not proof of a consistent improvement: Qwen's
delivery varies between requests. Connection reuse may not preserve vocal context
across commits. Listen for pitch, accent, energy, and pacing changes; compare
transitions in both versions and report the sample segment numbers. Article
extraction, segment packing, and production integration remain separate work.

Protocol reference: [Qwen WebSocket interaction flow](https://www.alibabacloud.com/help/en/model-studio/interactive-process-of-qwen-tts-realtime-synthesis)
and [client events](https://www.alibabacloud.com/help/en/model-studio/qwen-tts-realtime-client-events).

Validation includes deterministic session lifecycle/error tests and listening-page
state tests. A live run must also confirm the expected connection counts and valid,
nonempty audio for every segment. Perceptual consistency is assessed by listening.

## Numbered reference voice gallery

`/static/voice-gallery.html` presents 18 candidate reference samples. Voices appear
in this fixed order: Neil, Bellona, Elias, Vivian, Moon, Kai. Each voice has three
speeds in order: 1, 1.1, 1.25. Numbers are assigned before synthesis, so failures
never shift later numbers; Bellona at 1.1 is always sample #05 within a batch.
Each card has a fragment link for referring to its number. The batch ID is shown
under shared settings to distinguish later, explicitly generated batches.

After loading local credentials as above, generate the gallery with:

```bash
.venv/bin/python -m tts_app.experiments.voice_gallery
```

The command reads the saved session comparison manifest, taking its first original
paragraph and its model, language, instructions, and audio settings. Only voice and
synthesis speed differ. Each sample uses one complete response through the existing
provider. There is no browser speed adjustment. `--source` selects another saved
comparison manifest and `--output` changes the artifact directory.

Outputs are private, ignored files under `static/voice-gallery-data/<run-id>/`,
excluded from packaged assets. The manifest is atomically updated after each sample
and records queued/generating/completed/failed status. Refreshing the gallery only
reads these files. Failed samples remain labelled and are not automatically retried;
the command returns nonzero if any fail. A new invocation creates a new batch and
preserves earlier files. As with the session lab, there are no SQLite relationships
or automatic deletion; removing an experiment's directory requires an explicit
manual action. No app generations or profiles are changed.

These are built-in voice candidates. Voice enrollment/cloning waits for the user's
sample selection, after which a short reference excerpt can be chosen and tested
against multiple independent passages. No custom provider voices are created here.

## Selected voice cloning comparison

The user selected #16 Kai (1×), #11 Vivian (1.1×), #06 Bellona (1.25×), and #01 Neil
(1×). `/static/clone-lab.html` keeps these numbers and provides an original/cloned
comparison for each, plus the selected reference recording.

After loading local credentials, run:

```bash
.venv/bin/python -m tts_app.experiments.clone_lab
```

This performs four paid voice enrollments and 24 TTS requests: three original and
three cloned passages per selected voice. The reference recordings are copied
unchanged from the gallery (about 32–37 seconds, within Qwen's 60-second maximum).
They contain the entire reference paragraph. Qwen rejected enrollment with the
optional transcript field, so enrollment uses the documented audio-only request
with `language=en`. No trimming, volume normalization, or speed editing is applied.

`qwen_enrollment.py` owns HTTP enrollment and binds voices to the pinned
`qwen3-tts-vc-realtime-2026-01-15` model. It uploads a base64 WAV directly to the
configured Qwen region, without making the reference publicly accessible. No
credentials or audio payloads are logged. Returned voice IDs, model, request ID,
and any fallback-quality indicator are recorded immediately in the local manifest;
the page displays a fallback notice if the provider reports one.

The three test passages use the remaining five paragraphs from the source
comparison, grouped as two, two, and one. They exclude the enrollment paragraph.
Both versions use the same passage grouping and requested speed, with each passage
generated through a separate session. The original uses its saved instruction model
and audiobook instructions. The clone uses its saved voice ID and the cloning
model, with empty instructions because that model has no equivalent support. This
compares the two complete narration setups, not cloning as the sole variable.

The runner checkpoints each completed segment under ignored
`static/clone-lab-data/<run-id>/` and then joins the PCM audio into comparison WAVs.
Boundary positions come from actual frame counts, without adding silence. It
retains original reference copies, individual audio, combined audio, and enrolled
voice metadata. Provider failures are recorded without automatic retries.

Explicit continuation after an interruption or corrected failure:

```bash
.venv/bin/python -m tts_app.experiments.clone_lab --resume src/tts_app/static/clone-lab-data/latest.json
```

Continuation reuses saved enrollment IDs and completed audio. A new invocation
without `--resume` creates a separate experiment and four new voices. If enrollment
times out or is interrupted before its returned ID is saved, inspect the provider's
voice list using the manifest's `preferred_name` before repeating enrollment.
No automatic enrollment retry, voice deletion, or production profile integration
is performed. Locally deleting experiment files does not delete enrolled voices
from the provider account; cloud cleanup requires a separate explicit API action.
Preserve the manifests while keeping those voices. All artifacts remain excluded
from Git and packaged static assets.

Enrollment reference: [Qwen voice cloning HTTP API](https://www.alibabacloud.com/help/en/model-studio/voice-clone-design-http-api).
