# Reliable background generation and recovery

Approved direction: bound provider waits, retain completed audio, resume unfinished segments with the original snapshot, and recover interrupted work after restart. Browser closure must not cancel generation. No automatic synthesis retries in this first version.

## Behaviour

A server-owned task processes Text, URL and reviewed OCR generations independently of the HTTP request or browser event subscription. Reopening an active generation reads current persisted progress and reconnects live updates. SQLite remains the durable source of state; the single-process application owns active tasks.

Provider requests wait for session creation and settings acknowledgement. Configurable defaults: connect/setup/send 15 seconds, audio inactivity 60 seconds, whole segment 180 seconds; close is bounded to 5 seconds. Non-audio events do not indefinitely extend the audio deadline. Errors retain phase, code, request/session identifiers and elapsed time, with no credentials, input text or audio logged.

History offers Resume for failed generations with a usable saved synthesis snapshot. Resume uses the existing generation ID, original text segments and snapshot, without reading mutable profiles or fetching a URL again. Completed segment files and playback position are preserved. Only unfinished segments are synthesized. No invented historical model metadata: incompatible historical entries explain why Resume is unavailable.

A single active task per generation is enforced before scheduling. Shutdown cancels owned jobs and marks them failed with an interruption reason. Startup marks abandoned queued/running jobs interrupted and resumable; it never automatically starts paid work. Deletion cancels and awaits owned work before deleting durable assets.

Segment audio is written to a temporary file then atomically renamed only after provider completion. Segment completion and audio metadata are committed in one SQLite transaction. Resume validates saved completed files and refuses inconsistent checkpoints rather than silently overwriting completed audio. Combined audio is rebuildable from completed segments and must not gain duplicates during resume.

## Boundaries and verification

Provider protocol/diagnostics remain in providers; generation persists checkpoints; a focused job runner owns task lifetime; generation recovery routes stay separate from the app factory; history.js owns Resume UI; a small frontend subscription helper owns reconnect/refresh. No extra queue service or frontend framework.

Verify protocol stalls and errors, disconnect independence, partial completion/resume, snapshot immutability, duplicate Resume, cancellation/deletion, restart recovery, corrupt/missing completed audio, combined-file consistency, and browser reopen. Run required Python and JS checks, architecture review and one live Qwen canary in temporary storage. Do not change production data or switch the running checkout during implementation.
