# Agent handoff — birdnet fork state and gotchas

Orientation notes for a future AI agent (or future me) picking up the
speech-redaction work. Written 2026-08-03 after reviewing the
`redaction-mic-integration` branch of https://github.com/hermes-mighdz/birdnet.
Read this alongside `project.md` (current status) before touching anything.

## The two-repo split (do not confuse them)

- **This repo (project-sage-notes)** — design docs and the *canonical* pure
  redaction modules (`code/redaction/`): `RedactionGate`, `speech_classes`,
  the TF-Hub `yamnet_speech`, and their 22 tests.
- **The fork (hermes-mighdz/birdnet, branch `redaction-mic-integration`)** —
  the integration into the actual node application. On the Thor it imports the
  canonical modules **unchanged** from a local clone of this repo at
  `/home/mighdz/AI-Projects/notes-ref/code/redaction` (path hardcoded in
  `redaction/scripts/run_redaction_on_capture.py:34`). If you change
  `redaction_gate.py` or `speech_classes.py` here, the node's `notes-ref`
  clone must be pulled or the fork runs stale copies.
- Trap: `yamnet_speech.py` exists in BOTH repos and they are **different
  files**. This repo's version loads TF-Hub (works on dev machines, not on the
  Thor). The fork's `redaction/yamnet_speech.py` is a LiteRT rewrite with a
  model-path fallback chain. Same public API (`speech_scores`), different
  backends. Never copy one over the other.

## What is real vs proposed on the fork (as of 334c8cd)

- **Done and validated:** mic-path integration (`redact_speech` wired into
  `record_from_microphone` before `sample.save()`, commit `cbcb2fa`);
  `redaction/apply.py` with the fail-closed invariant; 43 tests passing;
  end-to-end run on real speech (see `REDACTION-VALIDATION-LOG.md` — real
  numbers, 2 windows, 82.4% of a 20.86s clip redacted, window math verified
  by hand against the gate's parameters).
- **Built but not meaningful yet:** `redaction/scripts/tune_thresholds.py`
  (enter-threshold sweep, recall vs FPR). Only ever run on a 3-clip set that
  separates too cleanly to pick an operating point. Do not cite its output as
  "tuned thresholds."
- **Proposed only, no code:** `redaction/CAMERA-PATH-DESIGN.md` (ffmpeg
  stdout-pipe for the camera path + audio/video time-windowing). The doc
  itself says PROPOSED — NOT BUILT in line one. Keep it that way in any
  status you write.
- **Not yet done anywhere:** live capture through a physical mic on the node
  (all validation so far reads files), and threshold tuning on a
  representative labeled set.

## Invariants you must not break

- **Fail closed, whole-buffer:** `redaction/apply.py::redact_speech` zeroes
  the ENTIRE buffer and returns a reason string on any scoring/gate failure.
  It never returns the raw array on an error path. Any refactor must preserve
  this; it is the load-bearing privacy guarantee.
- **Redact before persistence:** the mic-path insertion point is between
  `mic.record()` and `sample.save()`. Nothing may write `sample.data` to disk
  before `redact_speech` has run on it.
- **Frame math:** YAMNet frames are 0.96s long with a 0.48s hop (they
  overlap). Segment ends are `last_frame*hop + frame_duration`, not
  `(last_frame+1)*hop`. This bug was found and fixed once; tests in both
  repos pin it.
- **Windows are wall-clock seconds.** `speech_scores` resamples to 16kHz
  internally, but returned windows are converted back to sample indices at
  the ORIGINAL capture rate (48kHz on the mic). Keep it that way.
- **Deliberate divergence in the tuning harness:** `tune_thresholds.py`
  treats a fail-closed exception as "not flagged" because it measures the
  gate's binary decision, not the safety posture. That is intentional and
  documented in its docstring — do not "fix" it to match production, and do
  not copy its exception-swallowing into production code.

## Model file (yamnet.tflite) — paths and a known inconsistency

- Persistent location on H032: `/home/mighdz/AI-Projects/models/yamnet.tflite`
  (~15MB). Env override: `BIRDNET_YAMNET_TFLITE`. The fork's
  `redaction/yamnet_speech.py` resolves env var → container path → dev
  scratch.
- **Known inconsistency to fix:** `run_redaction_on_capture.py:42` still
  hardcodes `YAMNET_TFLITE = "/tmp/yamnet.tflite"`, which a reboot wipes.
  The durability commit (`c96836f`) updated the docs and the module resolver
  but not this script. After a Thor reboot the validation/tuning scripts will
  error (or worse, silently fail closed) until the script is pointed at the
  persistent path or the resolver.
- Failure signature worth knowing: if the model file is missing in
  production, every capture fails closed → silence-only FLACs → BirdNET
  detections flatline with no crash. If detections mysteriously stop, check
  the model path before debugging BirdNET.

## LiteRT quirks (aarch64 Thor, no full TF at runtime)

- The TFLite converter froze the input dim to `[1]`; call
  `resize_tensor_input(in_idx, [len(waveform)])` + `allocate_tensors()` per
  clip.
- Select the score tensor by `shape[-1] == 521`, not by output name — the
  converter mangles names (`StatefulPartitionedCall:0`).
- XNNPACK CPU delegate is sufficient; no GPU needed for YAMNet.

## Working norms for this project (learned the hard way)

- Miguel is the sole commit author. No AI co-author trailers, ever.
- Show diffs before committing when he asks; keep commit messages terse,
  matching the existing style.
- Status language is honest and load-bearing: "proposed" ≠ "built",
  "verified on 3 clips" ≠ "tuned". Pete reads these docs; do not upgrade
  claims.
- Expect concurrent pushes: edits land on the repos from the Mac, the node,
  and Hermes sessions. Always `git fetch` and inspect before pushing;
  rebase-and-resolve keeping the reviewed local wording has been the pattern.
- The Mac has SSH config for the Thors (`ssh waggle-dev-node-H032` via the
  beekeeper proxy), but do not SSH to the node without being asked.
- Node etiquette: H00F is busy/shared — use H032 (or another quiet Thor).
