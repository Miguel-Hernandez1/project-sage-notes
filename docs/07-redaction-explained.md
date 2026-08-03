# Speech redaction, explained simply

My notes on the redaction system, written so I can re-learn
this later or walk someone through it without opening the dense technical
docs. The precise versions live on the birdnet fork
(`REDACTION-SYSTEM-OVERVIEW.md`, `REDACTION-INTEGRATION-NOTES.md`)

## The problem in one paragraph

Sage is putting a sensor node in Haleakalā National Park. The Park Service
doesn't want visitors' voices recorded, so they asked for the microphone to
be off. Our answer: keep the mic on for birds, but make it *impossible* for
human speech to be saved. Every audio clip gets checked for speech before it
ever touches disk, and any speech gets erased (zeroed out) first. BirdNET
then runs on the already-cleaned audio and never knows the difference.

## How a capture flows through the system

Five steps, every cycle:

1. **Record.** The mic records ~15s of audio. At this moment the audio only
   exists as an array of numbers in memory — nothing is saved yet. This
   ordering is the entire trick: we get to inspect and edit the audio while
   it's still just memory.
2. **Score.** YAMNet (a small Google audio model) looks at the clip in
   ~1-second frames, sliding forward half a second at a time, and gives each
   frame a 0-to-1 score for "does this sound like human speech?" We don't
   just check its "Speech" class — we take the highest score across 12
   speech-family classes (whispering, shouting, child speech, etc.), because
   mumbled or distant speech can light up a neighbor class while scoring low
   on "Speech" itself.
3. **Decide.** The `RedactionGate` turns those per-frame scores into time
   windows to erase. It works like a thermostat: it takes a score of 0.25 to
   *start* redacting, but once redacting, the score has to stay below 0.15
   for a while before it *stops*. That gap (hysteresis) stops the gate from
   flickering on/off between words in a sentence. It also pads every window:
   1.5s backward (speech onset is detected late) and ~0.75s forward
   (trailing syllables).
4. **Erase.** The samples inside those windows are overwritten with zeros,
   directly in the in-memory array. There's no "original" left — the raw
   speech is gone before anything is saved.
5. **Save and classify.** Only now does the (already-clean) audio get
   written to a temp file for BirdNET. Everything downstream — species
   detection, publishing, uploads — sees redacted audio only.

## "Fail closed" — the most important idea in the whole system

Question: what should happen if the speech detector *breaks*? Model file
missing, inference crashes, whatever.

Wrong answer: "no speech detected, save the audio." That publishes raw
voices exactly when the safety system is down.

Our answer: **if we can't check for speech, we assume ALL of it is speech**
and zero the entire clip. The node saves silence and logs a warning. This is
called failing closed (like a door that locks when the power goes out,
instead of swinging open).

The code enforces this at three layers, so even a bug in one layer doesn't
leak audio: `redact_speech` itself zeroes everything if scoring fails; the
caller in `app.py` has a backup catch that zeroes everything if an error
somehow escapes; and a final catch-all handles anything unexpected. Even a
Ctrl-C mid-capture is safe — the save step just never runs.

Side effect worth remembering: if the model file goes missing on a deployed
node, every clip becomes silence and BirdNET detections flatline *with no
crash*. So "the node went scientifically quiet" is a symptom to check the
redaction gate for, not just BirdNET.

## Two different "confidence" numbers — don't mix them up

This confused me at first, so spelling it out:

- **BirdNET confidence** (e.g. "Northern Cardinal, 0.71") is the bird
  classifier's per-species probability. It decides what detections get
  *published* and which clips get *uploaded*.
- **YAMNet speech score** (the 0-to-1 per-frame number) feeds the redaction
  gate and nothing else.

They come from different models with different calibrations. A 0.25 speech
score and a 0.25 bird confidence are not comparable numbers, and neither one
is a true "probability."

## Why the thresholds are what they are (and why they're not final)

The gate defaults (enter 0.25 / exit 0.15, generous padding) are deliberately
paranoid. The cost math is lopsided: erasing a few extra seconds of birdsong
costs almost nothing, but leaking one syllable of a visitor's voice is a
privacy violation. So every knob is biased toward over-redacting. The VAD
research doc (`05-vad-hangover-research.md`) backs the padding scale with
sourced numbers from telephony/ASR systems — noting those systems tune the
*opposite* direction, so we pad more than they do.

But: these are still *design-choice* defaults, not measured ones. We built a
tuning harness (`tune_thresholds.py` on the fork) that sweeps the enter
threshold and reports recall vs false positives on labeled clips — it works,
but our 3-clip test set is too easy (perfect scores at every threshold), so
it can't pick a real operating point yet. Next step is a nastier labeled
set: distant/mumbled speech, and ambient sounds that fool YAMNet.

## Where things run and where files live

- The pure logic (`redaction_gate.py`, `speech_classes.py`) is identical in
  this repo and the fork — the fork imports it unchanged.
- On the Thor, YAMNet runs as a `.tflite` file through LiteRT (the TF Hub
  loader in this repo's `yamnet_speech.py` doesn't work on the node — the
  fork has a LiteRT version with the same interface).
- The model file lives at `~/AI-Projects/models/yamnet.tflite` on H032 so it
  survives reboots (`/tmp` gets wiped), with a `BIRDNET_YAMNET_TFLITE` env
  var to override. Production containers will bake it into the image.

## Timeline — what happened, in order (maps to fork commits)

1. **Found the architecture problem** (`77108c7`, Jul 27). The stock birdnet
   app saves raw audio to disk *before* any classification. A downstream
   filter can't fix that — redaction has to happen before the save. Mapped
   the exact insertion point in `record_from_microphone`.
2. **Proved YAMNet runs on the Thor** (same commit). No TF Hub / no network
   on nodes, so: downloaded YAMNet, converted it to `.tflite`, ran it via
   LiteRT on the ARM cores. Verified all 16 speech class indices against the
   canonical CSV (an earlier lesson: an LLM confidently gave us two class
   names that don't exist).
3. **Validated end-to-end on real speech** (`cf30059`, Jul 28). Ran a real
   ~21s speech clip through YAMNet + the gate on the Thor: scores sat at
   ~0.01 in silence, ~0.99 during speech, and the gate produced exactly the
   windows the math predicts (82% of that clip redacted). Wrote it up in
   `REDACTION-VALIDATION-LOG.md` with the full frame-by-frame numbers.
4. **Built the glue and landed the integration** (`7b92793` + `cbcb2fa`,
   Jul 29). `redaction/apply.py` (the fail-closed `redact_speech` wrapper)
   plus the actual wiring into `record_from_microphone`, with the
   three-layer error handling. 14 new tests on the fork (43 total passing).
   Also a demo flag (`--write-redacted`) that produces before/after audio.
5. **Hardened and prepped tuning** (Aug 3: `408b36b`, `c96836f`, `abf9bc8`).
   Threshold-sweep harness; moved the model to a reboot-proof path; wrote
   the camera-path design doc (proposal only — the camera records through
   ffmpeg straight to disk, so it needs a stdout-pipe redesign to get the
   same guarantee; not built yet).

## What's genuinely still open

- Live test with a physical mic on the node (everything so far used recorded
  files pushed through the same code path).
- The camera path (design proposal exists, zero code).
- Real threshold tuning (needs the harder labeled clip set).
- A published `redaction.event` measurement so a deployed node's redactions
  are observable — otherwise you can't tell a quiet forest from a broken
  gate. Pending, and Pete still needs to sign off on silence-vs-comfort-noise.
