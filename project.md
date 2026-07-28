# Speech Redaction at the Edge for BirdNET Audio

**Miguel Hernandez** — Northwestern University
Sage Grande Summer of AI 2026

## Problem

Sage is deploying a node at Haleakalā National Park. The National Park
Service does not want park visitors recorded, and has asked that the
microphone be turned off. The goal of this project is to offer an
alternative: automatic redaction of human speech at the edge, so the node
can still run BirdNET bird-call classification while guaranteeing that human
speech is never persisted.

The core requirement is a hard one: it should be **impossible** to
accidentally record human speech. That means the guarantee has to hold even
when the speech detector fails.

## Key finding: the pipeline persists audio before it classifies it

The existing `flint-pete/birdnet` node application writes every capture to a
temporary FLAC file *before* any classification runs, on both audio paths:

- **Microphone path** (`record_from_microphone`, app.py:160-178): pywaggle's
  `Microphone.record()` returns an in-memory `AudioSample`, but the code
  immediately calls `sample.save()` to a temp FLAC before doing anything else.
- **Camera path** (`record_from_camera`, app.py:181-237): ffmpeg writes the
  capture straight to disk; the PCM samples never exist as a Python array.

This means redaction cannot be a downstream filter — by the time BirdNET runs,
raw speech is already on disk. Redaction has to happen **before persistence**.

The microphone path is fixable: `sample.data` is a 1-D float32 array available
in memory before `save()`. Redaction can operate on that array in place, and
only the already-redacted array is written. The camera path is harder and
would require piping ffmpeg to stdout to decode in-process.

## Design principle

The safe default state of the system is **redacting**. Successful speech
classification is what *permits* recording, not what triggers redaction. If
the classifier fails or returns nothing, the system redacts rather than
publishes. This is the "fail closed" principle, and it is enforced in the code.

## What I built

Three tested Python modules (all with unit tests, verified against source
rather than assumed):

**`RedactionGate`** — a hysteresis state machine that takes per-frame speech
scores and returns the time ranges to redact. Configurable enter/exit
thresholds (low bar to enter redaction, higher bar to exit, so it doesn't
flicker mid-sentence), pre-roll padding, hangover (gap tolerance), and
post-roll padding. Fails closed on empty input.

- Caught and fixed a real bug: YAMNet frames are 0.96s long with a 0.48s hop,
  so they overlap. Naive frame-hop math under-redacted the tail of every
  speech segment by 0.48s. Fixed by tracking frame duration separately from
  hop.

**`speech_classes.py`** — the verified YAMNet AudioSet speech class indices,
checked against the canonical `yamnet_class_map.csv`, split into core speech
classes and ambiguous ones (crowd, chatter, children). Reduces a 521-class
YAMNet frame vector to a single speech score by taking the max across the
speech family. (Note: "Male speech" and "Female speech" are not YAMNet
classes — a detail worth verifying rather than assuming.)

**`yamnet_speech.py`** — wraps YAMNet to turn a raw audio array into
per-frame speech scores: resample to 16kHz mono, run YAMNet, reduce each
frame through `speech_classes`. Model load is lazy and cached.

## What has been verified on hardware (Jetson AGX Thor, aarch64)

The speech-detection inference has been run on the Thor node itself:

- YAMNet's SavedModel loads and converts to TFLite on the Thor.
- The TFLite model runs via `ai_edge_litert` on the ARM cores with the
  XNNPACK CPU delegate — no GPU needed.
- Sanity check passes: on silence, YAMNet correctly reports class 494
  "Silence" at 1.0 and class 0 "Speech" at 0.0.
- 3 seconds of audio produces 6 frames, matching the expected 0.48s hop.

This answers a key open question — whether the speech detector can run on the
target hardware — with a demonstrated yes.

**Not yet tested:** live audio capture from the camera or microphone. No real
hardware audio has been captured or run through the pipeline end-to-end yet;
the modules above have been validated with unit tests and synthetic input, and
YAMNet inference has been validated on the node. Live capture and
threshold tuning against real audio are the immediate next steps below.

## Grounded parameter choices

Padding and threshold choices are backed by sourced research on voice
activity detection hangover timing (WebRTC VAD, NVIDIA Riva/Silero, 3GPP AMR
specs) rather than guessed. Telephony VAD uses 60-580ms hangover, but that is
tuned for the opposite cost trade-off (don't waste bandwidth on silence). For
privacy redaction, where under-redacting is far more costly, the recommended
guard is ~1s post-utterance with a longer hold when the signal is
non-stationary.

## Redaction as a data product

Rather than filling redacted spans with comfort noise (which would corrupt
the bioacoustic record BirdNET and downstream soundscape analysis depend on),
the plan is to write silence plus publish a separate `audio.redacted`
measurement with timestamp and duration. This makes each redaction auditable,
distinguishable from a dead sensor, and gives NPS a verifiable log — while
also yielding free statistics on human presence at the site.

## Architecture

```
mic capture (in-memory array)
   -> YAMNet speech scoring (per 0.48s frame)
   -> RedactionGate (hysteresis -> redaction time windows)
   -> zero out speech samples in the array
   -> BirdNET classification + publish
   -> publish redaction event (timestamp, duration)
   (raw unredacted array never touches disk)
```

## Next steps

- Wire the redaction modules into the microphone path in `app.py` (insertion
  point mapped: between the in-memory array and the save call).
- RTSP/audio bring-up with the Reolink camera: confirm the camera exposes
  audio, and test whether ffmpeg can pipe it without writing to disk.
- Tune enter/exit thresholds against real recorded speech at varying distance
  and volume, plotting recall vs threshold to hit a target recall (99%+) and
  reporting the precision cost.
- Define the `audio.redacted` measurement schema for Beehive.

## Repositories

- Notes, design docs, and redaction modules:
  https://github.com/Miguel-Hernandez1/project-sage-notes
- Integration analysis (birdnet fork):
  https://github.com/hermes-mighdz/birdnet

## Acknowledgment

This work was supported in part by the National Science Foundation under
Awards No. 2331263 and 2436842.
